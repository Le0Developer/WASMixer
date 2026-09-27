"""Small SSA IR and Cytron conversion utilities used by the mutator.

The IR is deliberately independent of Wasm encoding. A front end supplies
basic blocks with local-variable reads and writes; this module computes
dominators, dominance frontiers, phi placement, and renamed SSA values.
"""

from collections import defaultdict
from dataclasses import dataclass, field


@dataclass(eq=False)
class SSAValue:
    """One SSA definition."""

    ident: int
    variable: object
    kind: str
    block: object
    instruction: object = None
    inputs: list = field(default_factory=list)


@dataclass
class SSAOperation:
    """An operation in a basic block; reads/writes name source variables."""

    instruction: object
    reads: tuple = ()
    writes: tuple = ()
    values_in: list = field(default_factory=list)
    values_out: list = field(default_factory=list)


@dataclass(eq=False)
class BasicBlock:
    name: object
    operations: list = field(default_factory=list)
    successors: set = field(default_factory=set)
    predecessors: set = field(default_factory=set)
    phis: dict = field(default_factory=dict)

    def connect(self, successor):
        self.successors.add(successor)
        successor.predecessors.add(self)


class SSAFunction:
    """Convert a variable-oriented CFG to SSA form, including loop phis."""

    def __init__(self, blocks, entry, initial_variables=()):
        self.blocks = list(blocks)
        self.entry = entry
        self.initial_variables = tuple(initial_variables)
        self.values = []
        self.dominators = {}
        self.idom = {}
        self.frontiers = {}

    def _reachable(self):
        seen = set()
        todo = [self.entry]
        while todo:
            block = todo.pop()
            if block in seen:
                continue
            seen.add(block)
            todo.extend(block.successors - seen)
        return seen

    def _compute_dominators(self, reachable):
        dom = {block: ({block} if block is self.entry else set(reachable))
               for block in reachable}
        changed = True
        while changed:
            changed = False
            for block in reachable:
                if block is self.entry:
                    continue
                preds = block.predecessors & reachable
                common = set.intersection(*(dom[pred] for pred in preds)) if preds else set()
                updated = common | {block}
                if updated != dom[block]:
                    dom[block] = updated
                    changed = True

        idom = {self.entry: None}
        for block in reachable - {self.entry}:
            strict = dom[block] - {block}
            idom[block] = next(
                (candidate for candidate in strict
                 if all(other is candidate or other in dom[candidate]
                        for other in strict)),
                None,
            )

        frontier = {block: set() for block in reachable}
        for block in reachable:
            preds = block.predecessors & reachable
            if len(preds) < 2:
                continue
            for pred in preds:
                runner = pred
                while runner is not None and runner is not idom[block]:
                    frontier[runner].add(block)
                    runner = idom[runner]

        self.dominators = dom
        self.idom = idom
        self.frontiers = frontier

    def _place_phis(self, reachable):
        definitions = defaultdict(set)
        variables = set(self.initial_variables)
        for block in reachable:
            for operation in block.operations:
                variables.update(operation.reads)
                for variable in operation.writes:
                    variables.add(variable)
                    definitions[variable].add(block)

        for variable in variables:
            work = list(definitions[variable])
            placed = set()
            while work:
                block = work.pop()
                for frontier_block in self.frontiers[block]:
                    if frontier_block in placed:
                        continue
                    phi = SSAValue(-1, variable, "phi", frontier_block)
                    frontier_block.phis[variable] = phi
                    placed.add(frontier_block)
                    if frontier_block not in definitions[variable]:
                        work.append(frontier_block)

    def _rename(self, reachable):
        children = defaultdict(list)
        for block, parent in self.idom.items():
            if parent is not None:
                children[parent].append(block)

        counters = defaultdict(int)
        stacks = defaultdict(list)

        def define(variable, kind, block, instruction=None, inputs=None):
            value = SSAValue(counters[variable], variable, kind, block,
                             instruction, inputs or [])
            counters[variable] += 1
            stacks[variable].append(value)
            self.values.append(value)
            return value

        for variable in self.initial_variables:
            define(variable, "parameter", self.entry)

        def visit(block):
            pushed = defaultdict(int)
            for variable in block.phis:
                define(variable, "phi", block)
                pushed[variable] += 1

            for operation in block.operations:
                operation.values_in = []
                for variable in operation.reads:
                    if not stacks[variable]:
                        raise ValueError(
                            "SSA read of variable without an initial definition: "
                            + repr(variable)
                        )
                    operation.values_in.append(stacks[variable][-1])
                operation.values_out = []
                for variable in operation.writes:
                    operation.values_out.append(
                        define(variable, "instruction", block, operation.instruction)
                    )
                    pushed[variable] += 1

            for successor in block.successors & reachable:
                for variable, phi in successor.phis.items():
                    if not stacks[variable]:
                        raise ValueError(
                            "SSA phi input without an initial definition: "
                            + repr(variable)
                        )
                    phi.inputs.append((block, stacks[variable][-1]))

            for child in children[block]:
                visit(child)
            for variable, count in pushed.items():
                del stacks[variable][-count:]

        visit(self.entry)
        for block in reachable:
            for phi in block.phis.values():
                phi.inputs.sort(key=lambda item: repr(item[0].name))

    def convert(self):
        """Compute SSA form in place and return this function."""
        reachable = self._reachable()
        if self.entry not in reachable:
            return self
        self._compute_dominators(reachable)
        self._place_phis(reachable)
        self._rename(reachable)
        return self


def build_wasm_local_cfg(instructions, local_count):
    """Build a structured-control CFG and SSA-convert Wasm local variables.

    Each source instruction is kept in its own block. Local reads and writes
    become SSA uses and definitions, with phi nodes at branch joins and loop
    headers. Operand-stack values are not converted by this local-variable
    front end.
    """
    entry = BasicBlock("entry")
    blocks = [entry]
    serial = 0

    def new_block(prefix):
        nonlocal serial
        serial += 1
        block = BasicBlock((prefix, serial))
        blocks.append(block)
        return block

    def local_operation(block, instr):
        from WASMixer.parser.opcodes import LocalGet, LocalSet, LocalTee

        if instr.opcode == LocalGet:
            block.operations.append(SSAOperation(instr, reads=(instr.args,)))
        elif instr.opcode == LocalSet:
            block.operations.append(SSAOperation(instr, writes=(instr.args,)))
        elif instr.opcode == LocalTee:
            block.operations.append(SSAOperation(
                instr, reads=(instr.args,), writes=(instr.args,)
            ))
        else:
            block.operations.append(SSAOperation(instr))

    def lower(seq, current, labels):
        from WASMixer.parser.instruction import BlockArgs, IfArgs
        from WASMixer.parser.opcodes import (
            Block, Br, BrIf, BrTable, If, Loop, Return, Unreachable,
        )

        for instr in seq:
            if current is None:
                # Instructions after an unconditional transfer in this
                # structured region are unreachable on its fallthrough path.
                continue
            opcode = instr.opcode
            if opcode in (Block, Loop):
                target = new_block("block_exit" if opcode == Block else "loop_exit")
                header = current
                if opcode == Loop:
                    header = new_block("loop_header")
                    current.connect(header)
                label_target = header if opcode == Loop else target
                body = instr.args.instrs if isinstance(instr.args, BlockArgs) else []
                end = lower(body, header, labels + [label_target])
                if end is not None:
                    end.connect(target)
                current = target
                continue

            if opcode == If:
                args = instr.args if isinstance(instr.args, IfArgs) else None
                join = new_block("if_join")
                then_entry = new_block("if_then")
                else_entry = new_block("if_else")
                current.connect(then_entry)
                current.connect(else_entry)
                label_stack = labels + [join]
                then_end = lower(args.instrs1 if args else [], then_entry, label_stack)
                else_end = lower(args.instrs2 if args else [], else_entry, label_stack)
                if then_end is not None:
                    then_end.connect(join)
                if else_end is not None:
                    else_end.connect(join)
                current = join
                continue

            if opcode in (Br, BrIf, BrTable):
                if opcode == Br:
                    depths = [instr.args]
                elif opcode == BrIf:
                    depths = [instr.args]
                else:
                    depths = list(instr.args.labels) + [instr.args.default]
                for depth in depths:
                    if depth < len(labels):
                        current.connect(labels[-1 - depth])
                if opcode == Br:
                    current = None
                    continue
                if opcode == BrIf:
                    continuation = new_block("br_if_continue")
                    current.connect(continuation)
                    current = continuation
                    continue
                current = None
                continue

            local_operation(current, instr)
            if opcode in (Return, Unreachable):
                current = None
                continue
            next_block = new_block("instruction")
            current.connect(next_block)
            current = next_block

        return current

    tail = lower(instructions, entry, [])
    if tail is not None:
        exit_block = new_block("function_exit")
        tail.connect(exit_block)
    return SSAFunction(blocks, entry, initial_variables=range(local_count)).convert()
