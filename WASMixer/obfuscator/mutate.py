"""Semantics-preserving instruction mutations for core Wasm modules."""

import random

from WASMixer.parser.instruction import Instruction
from WASMixer.parser.module import Locals
from WASMixer.parser.opcodes import *
from WASMixer.parser.types import ValTypeI32, ValTypeI64
from .ssa import BasicBlock, SSAFunction, SSAOperation, build_wasm_local_cfg

I32_UNARY = {I32Eqz, I32Clz, I32Ctz, I32PopCnt}
I32_BINARY = {
    I32Eq, I32Ne, I32LtS, I32LtU, I32GtS, I32GtU, I32LeS, I32LeU,
    I32GeS, I32GeU, I32Add, I32Sub, I32Mul, I32And, I32Or, I32Xor,
    I32Shl, I32ShrS, I32ShrU, I32Rotl, I32Rotr,
}
I64_UNARY = {I64Eqz, I64Clz, I64Ctz, I64PopCnt}
I64_BINARY = {
    I64Eq, I64Ne, I64LtS, I64LtU, I64GtS, I64GtU, I64LeS, I64LeU,
    I64GeS, I64GeU, I64Add, I64Sub, I64Mul, I64And, I64Or, I64Xor,
    I64Shl, I64ShrS, I64ShrU, I64Rotl, I64Rotr,
}


class WasmMutator:
    """Mutate function code and schedule safe stack-expression regions."""

    def __init__(self, seed=None, preserve_semantics=True):
        if not preserve_semantics:
            raise ValueError("only semantics-preserving mutations are supported")
        self.rng = random.Random(seed)

    @staticmethod
    def _signed(value, bits):
        value &= (1 << bits) - 1
        sign_bit = 1 << (bits - 1)
        return value if value < sign_bit else value - (1 << bits)

    def _rewrite_constant(self, instr, bits):
        mask = (1 << bits) - 1
        value = instr.args & mask
        left = self.rng.getrandbits(bits)
        if self.rng.getrandbits(1):
            right = value ^ left
            opcode = I32Xor if bits == 32 else I64Xor
        else:
            right = (value - left) & mask
            opcode = I32Add if bits == 32 else I64Add

        const_opcode = I32Const if bits == 32 else I64Const
        return [
            Instruction(const_opcode, self._signed(left, bits)),
            Instruction(const_opcode, self._signed(right, bits)),
            Instruction(opcode),
        ]

    def _identity(self, bits):
        const_opcode = I32Const if bits == 32 else I64Const
        add_opcode = I32Add if bits == 32 else I64Add
        xor_opcode = I32Xor if bits == 32 else I64Xor
        left = self._signed(self.rng.getrandbits(bits), bits)

        if self.rng.randrange(3) == 0:
            return [
                Instruction(const_opcode, left), Instruction(xor_opcode),
                Instruction(const_opcode, left), Instruction(xor_opcode),
            ]
        if self.rng.randrange(2) == 0:
            right = self._signed(-left, bits)
            return [
                Instruction(const_opcode, left), Instruction(add_opcode),
                Instruction(const_opcode, right), Instruction(add_opcode),
            ]

        right = self._signed(self.rng.getrandbits(bits), bits)
        return [
            Instruction(const_opcode, left), Instruction(add_opcode),
            Instruction(const_opcode, right), Instruction(xor_opcode),
            Instruction(const_opcode, right), Instruction(xor_opcode),
            Instruction(const_opcode, left), Instruction(I32Sub if bits == 32 else I64Sub),
        ]

    @staticmethod
    def _integer_result_bits(instr, module, local_types):
        opcode = instr.opcode
        i32_ops = (
            opcode in {I32Load, I32Load8S, I32Load8U, I32Load16S, I32Load16U}
            or I32Eqz <= opcode <= I32GeU
            or I32Clz <= opcode <= I32Rotr
            or I32WrapI64 <= opcode <= I32TruncF64U
            or opcode in {
                I32Const, I32ReinterpretF32, I32Extend8S, I32Extend16S,
                I32TruncSatF32S, I32TruncSatF32U,
                I32TruncSatF64S, I32TruncSatF64U,
                MemorySize, MemoryGrow, TableSize, TableGrow, RefIsNull,
            }
        )
        i64_ops = (
            opcode in {
                I64Load, I64Load8S, I64Load8U, I64Load16S, I64Load16U,
                I64Load32S, I64Load32U, I64Const, I64ReinterpretF64,
                I64Extend8S, I64Extend16S, I64Extend32S,
                I64TruncSatF32S, I64TruncSatF32U,
                I64TruncSatF64S, I64TruncSatF64U,
            }
            or I64Eqz <= opcode <= I64GeU
            or I64Clz <= opcode <= I64Rotr
            or I64ExtendI32S <= opcode <= I64TruncF64U
        )
        if i32_ops:
            return 32
        if i64_ops:
            return 64

        if opcode == LocalGet and instr.args < len(local_types):
            if local_types[instr.args] == ValTypeI32:
                return 32
            if local_types[instr.args] == ValTypeI64:
                return 64
        elif opcode == GlobalGet:
            imported_globals = [
                item.desc.global_type.val_type
                for item in module.import_sec if item.desc.global_type is not None
            ]
            global_types = imported_globals + [item.type.val_type for item in module.global_sec]
            if instr.args < len(global_types):
                if global_types[instr.args] == ValTypeI32:
                    return 32
                if global_types[instr.args] == ValTypeI64:
                    return 64

        type_index = None
        if opcode == Call:
            imported_funcs = [
                item.desc.func_type
                for item in module.import_sec if item.desc.func_type is not None
            ]
            if instr.args < len(imported_funcs):
                type_index = imported_funcs[instr.args]
            else:
                defined_index = instr.args - len(imported_funcs)
                if defined_index < len(module.func_sec):
                    type_index = module.func_sec[defined_index]
        elif opcode == CallIndirect:
            type_index = getattr(instr.args, "type_idx", instr.args)

        if type_index is not None and type_index < len(module.type_sec):
            results = module.type_sec[type_index].result_types
            if len(results) == 1:
                if results[0] == ValTypeI32:
                    return 32
                if results[0] == ValTypeI64:
                    return 64
        return None

    @staticmethod
    def _rewrite_integer_binary(instr, temporary_locals, bits):
        left_local, right_local = temporary_locals
        const_opcode = I32Const if bits == 32 else I64Const
        add_opcode = I32Add if bits == 32 else I64Add
        sub_opcode = I32Sub if bits == 32 else I64Sub
        xor_opcode = I32Xor if bits == 32 else I64Xor
        or_opcode = I32Or if bits == 32 else I64Or
        and_opcode = I32And if bits == 32 else I64And
        def local_get(index):
            return Instruction(LocalGet, index)

        replacement = [
            Instruction(LocalSet, right_local),
            Instruction(LocalSet, left_local),
        ]
        if instr.opcode in [add_opcode, sub_opcode]:
            replacement.extend([
                local_get(left_local), Instruction(const_opcode, 0),
                local_get(right_local), Instruction(sub_opcode),
                Instruction(sub_opcode if instr.opcode == add_opcode else add_opcode),
            ])
        else:
            replacement.extend([
                local_get(left_local), local_get(right_local), Instruction(or_opcode),
                local_get(left_local), local_get(right_local), Instruction(and_opcode),
                Instruction(const_opcode, -1), Instruction(xor_opcode),
                Instruction(and_opcode),
            ])
        return replacement

    def _mutate_expr(self, expr, module, local_types, temporary_locals):
        mutated = []
        for instr in expr:
            if instr.opcode in [Block, Loop]:
                instr.args.instrs = self._mutate_expr(
                    instr.args.instrs, module, local_types, temporary_locals
                )
            elif instr.opcode == If:
                instr.args.instrs1 = self._mutate_expr(
                    instr.args.instrs1, module, local_types, temporary_locals
                )
                instr.args.instrs2 = self._mutate_expr(
                    instr.args.instrs2, module, local_types, temporary_locals
                )

            if instr.opcode == I32Const:
                mutated.extend(self._rewrite_constant(instr, 32))
            elif instr.opcode == I64Const:
                mutated.extend(self._rewrite_constant(instr, 64))
            elif instr.opcode in [I32Eqz, I32Eq, I32Ne] and self.rng.random() < 0.5:
                if instr.opcode == I32Eqz:
                    mutated.extend([Instruction(I32Const, 0), Instruction(I32Eq)])
                elif instr.opcode == I32Eq:
                    mutated.extend([Instruction(I32Xor), Instruction(I32Eqz)])
                else:
                    mutated.extend([
                        Instruction(I32Xor), Instruction(I32Eqz), Instruction(I32Eqz),
                    ])
            elif instr.opcode in [I64Eqz, I64Eq, I64Ne] and self.rng.random() < 0.5:
                if instr.opcode == I64Eqz:
                    mutated.extend([Instruction(I64Const, 0), Instruction(I64Eq)])
                elif instr.opcode == I64Eq:
                    mutated.extend([Instruction(I64Xor), Instruction(I64Eqz)])
                else:
                    mutated.extend([
                        Instruction(I64Xor), Instruction(I64Eqz), Instruction(I64Eqz),
                    ])
            elif (instr.opcode in [I32Add, I32Sub, I32Xor]
                  and 32 in temporary_locals and self.rng.random() < 0.5):
                mutated.extend(self._rewrite_integer_binary(instr, temporary_locals[32], 32))
            elif (instr.opcode in [I64Add, I64Sub, I64Xor]
                  and 64 in temporary_locals and self.rng.random() < 0.5):
                mutated.extend(self._rewrite_integer_binary(instr, temporary_locals[64], 64))
            else:
                mutated.append(instr)

            result_bits = self._integer_result_bits(instr, module, local_types)
            if result_bits is not None and self.rng.random() < 0.5:
                mutated.extend(self._identity(result_bits))
        return mutated

    @staticmethod
    def _pure_integer_op(instr, local_types):
        opcode = instr.opcode
        if opcode == I32Const:
            return 32, 0, 32
        if opcode == I64Const:
            return 64, 0, 64
        if opcode == LocalGet and instr.args < len(local_types):
            if local_types[instr.args] == ValTypeI32:
                return 32, 0, 32
            if local_types[instr.args] == ValTypeI64:
                return 64, 0, 64

        if opcode in I32_UNARY:
            return 32, 1, 32
        if opcode in I32_BINARY:
            return 32, 2, 32
        if opcode in I64_UNARY:
            return 64, 1, 32 if opcode == I64Eqz else 64
        if opcode in I64_BINARY:
            return 64, 2, 32 if I64Eq <= opcode <= I64GeU else 64
        return None

    def _topological_order(self, nodes):
        dependents = [[] for _ in nodes]
        dependency_counts = []
        for node_id, node in enumerate(nodes):
            dependency_counts.append(len(node["inputs"]))
            for dependency in node["inputs"]:
                dependents[dependency].append(node_id)
        ready = [node_id for node_id, count in enumerate(dependency_counts) if count == 0]
        order = []
        while ready:
            node_id = ready.pop(self.rng.randrange(len(ready)))
            order.append(node_id)
            for dependent in dependents[node_id]:
                dependency_counts[dependent] -= 1
                if dependency_counts[dependent] == 0:
                    ready.append(dependent)
        return order if len(order) == len(nodes) else None

    def _reorder_chunk(self, instructions, local_types, code):
        """Build SSA values for an expression region and schedule its DAG."""
        block = BasicBlock("expression")
        stack = []
        for instr in instructions:
            op_info = self._pure_integer_op(instr, local_types)
            if op_info is None:
                return None
            input_bits, arity, result_bits = op_info
            if len(stack) < arity:
                # This expression depends on values from before the chunk.
                # Leave it intact rather than guess their types or order.
                return None
            inputs = stack[-arity:] if arity else []
            if arity:
                del stack[-arity:]
                if any(block.operations[value].result_bits != input_bits for value in inputs):
                    return None
            node_id = len(block.operations)
            block.operations.append(SSAOperation(
                instruction=instr,
                reads=tuple(inputs),
                writes=(node_id,),
            ))
            # Keep the source type alongside its SSA definition for validation
            # and temporary-local allocation below.
            block.operations[-1].result_bits = result_bits
            stack.append(node_id)

        if len(block.operations) < 2:
            return None
        # Each virtual variable is defined exactly once in this block. The
        # shared converter also handles multi-block CFGs and phi placement;
        # this region has no control-flow edges, so its SSA graph is a DAG.
        SSAFunction([block], block).convert()
        value_for_variable = {
            operation.writes[0]: operation.values_out[0]
            for operation in block.operations
        }
        nodes = [
            {
                "instr": operation.instruction,
                "inputs": [
                    next(index for index, candidate in enumerate(block.operations)
                         if candidate.writes[0] == value.variable)
                    for value in operation.values_in
                ],
                "bits": operation.result_bits,
                "ssa": value_for_variable[operation.writes[0]],
            }
            for operation in block.operations
        ]
        order = None
        for _ in range(8):
            candidate = self._topological_order(nodes)
            if candidate != list(range(len(nodes))):
                order = candidate
                break
        if order is None:
            return None

        first_local = len(local_types)
        i32_count = sum(node["bits"] == 32 for node in nodes)
        i64_count = len(nodes) - i32_count
        if i32_count:
            code.locals.append(Locals(i32_count, ValTypeI32))
        if i64_count:
            code.locals.append(Locals(i64_count, ValTypeI64))
        node_locals = {}
        next_i32 = first_local
        next_i64 = first_local + i32_count
        for node_id, node in enumerate(nodes):
            if node["bits"] == 32:
                node_locals[node_id] = next_i32
                next_i32 += 1
            else:
                node_locals[node_id] = next_i64
                next_i64 += 1
        local_types.extend([ValTypeI32] * i32_count)
        local_types.extend([ValTypeI64] * i64_count)

        reordered = []
        for node_id in order:
            node = nodes[node_id]
            instr = node["instr"]
            for dependency in node["inputs"]:
                reordered.append(Instruction(LocalGet, node_locals[dependency]))
            reordered.append(instr)
            reordered.append(Instruction(LocalSet, node_locals[node_id]))
        reordered.extend(Instruction(LocalGet, node_locals[value]) for value in stack)
        return reordered

    def _reorder_expr(self, expr, local_types, code):
        reordered = []
        index = 0
        while index < len(expr):
            instr = expr[index]
            if instr.opcode in [Block, Loop]:
                instr.args.instrs = self._reorder_expr(instr.args.instrs, local_types, code)
                reordered.append(instr)
                index += 1
                continue
            if instr.opcode == If:
                instr.args.instrs1 = self._reorder_expr(instr.args.instrs1, local_types, code)
                instr.args.instrs2 = self._reorder_expr(instr.args.instrs2, local_types, code)
                reordered.append(instr)
                index += 1
                continue
            if self._pure_integer_op(instr, local_types) is None:
                reordered.append(instr)
                index += 1
                continue

            end = index + 1
            while (end < len(expr)
                   and self._pure_integer_op(expr[end], local_types) is not None):
                end += 1
            chunk = expr[index:end]
            reordered.extend(self._reorder_chunk(chunk, local_types, code) or chunk)
            index = end
        return reordered

    def mutate_module(self, module):
        """Mutate expressions and reorder eligible regions in parsed functions."""
        for func_index, code in enumerate(module.code_sec):
            if code.raw_body is None:
                type_index = module.func_sec[func_index]
                local_types = list(module.type_sec[type_index].param_types)
                for local in code.locals:
                    local_types.extend([local.type] * local.n)
                # Convert local reads/writes over the function's structured
                # control flow to SSA first. This creates phi values at if
                # joins and loop headers; if the CFG cannot be represented,
                # leave that function untouched rather than guess.
                try:
                    build_wasm_local_cfg(code.expr, len(local_types))
                except (IndexError, TypeError, ValueError):
                    continue
                func_instrs = list(self._walk(code.expr))
                temporary_locals = {}
                if any(instr.opcode in {I32Add, I32Sub, I32Xor} for instr in func_instrs):
                    temporary_locals[32] = (len(local_types), len(local_types) + 1)
                    code.locals.append(Locals(2, ValTypeI32))
                    local_types.extend([ValTypeI32, ValTypeI32])
                if any(instr.opcode in {I64Add, I64Sub, I64Xor} for instr in func_instrs):
                    temporary_locals[64] = (len(local_types), len(local_types) + 1)
                    code.locals.append(Locals(2, ValTypeI64))
                    local_types.extend([ValTypeI64, ValTypeI64])
                code.expr = self._mutate_expr(
                    code.expr, module, local_types, temporary_locals
                )
                code.expr = self._reorder_expr(code.expr, local_types, code)
        return module

    @classmethod
    def _walk(cls, expr):
        for instr in expr:
            yield instr
            if instr.opcode in [Block, Loop]:
                yield from cls._walk(instr.args.instrs)
            elif instr.opcode == If:
                yield from cls._walk(instr.args.instrs1)
                yield from cls._walk(instr.args.instrs2)
