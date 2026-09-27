from WASMixer.obfuscator.utils import *
from WASMixer.parser.instruction import IfArgs
from WASMixer.parser.types import FuncRef, FuncType, Limits, TableType
from typing import Optional, Union, Any


class CodeObfuscator:

    def __init__(self, binary):
        self.wasm_binary = binary

    def _ensure_type_index(self, func_type_id: Union[int, FuncType, Any]) -> Optional[int]:
        """
        Ensure func_type_id is an integer type index. If func_type_id is a FuncType,
        return its index in module.type_sec (append if missing). If it's already an int,
        return it. If it's neither, return None.
        """
        if isinstance(func_type_id, int):
            return func_type_id
        if isinstance(func_type_id, FuncType):
            # try to find an identical type
            for ti, t in enumerate(self.wasm_binary.module.type_sec):
                if hasattr(t, 'param_types') and t.param_types == func_type_id.param_types and t.result_types == func_type_id.result_types:
                    return ti
            # not found: append and return new index
            self.wasm_binary.module.type_sec.append(func_type_id)
            return len(self.wasm_binary.module.type_sec) - 1
        return None

    def instr_flatten(self, instr_list, split_num, block_type, func_id, Collatz_func_id=None):

        # Some proposal instructions do not have a stack model in
        # opcodes_stack.py. Keep such functions intact instead of flattening
        # them with an incomplete stack snapshot.
        if get_instrs_max_stack_depth(self.wasm_binary, instr_list) == -1:
            return instr_list

        return_exist = False
        if instr_list[len(instr_list) - 1].opcode == Return:
            return_exist = True

        jump_flag_local = self.wasm_binary.add_new_local_to_func(func_id, ValTypeI32)

        try:
            code_blocks, new_local_i32, new_local_i64, new_local_f32, new_local_f64 = code_block_splitting(
                self.wasm_binary, instr_list, split_num, func_id
            )
        except UnsupportedStackType:
            return instr_list

        basic_blocks = []
        for cb in code_blocks:
            basic_blocks.append(cb['instrs'])

        # Build distribution block
        br_table_list = list(range(len(basic_blocks) + 1))
        dispatcher_instrs = [Instruction(LocalGet, jump_flag_local),
                             Instruction(BrTable, BrTableArgs(br_table_list, 0))]

        dispatcher_block = Instruction(Block, BlockArgs(BlockTypeEmpty, dispatcher_instrs))

        for _, bb in enumerate(basic_blocks):
            for instr in bb:
                if instr.opcode in [Br, BrIf]:
                    instr.args += len(basic_blocks) - _ + 1 + 1
                # elif instr.opcode == BrTable:
                #     for label_id in instr.args.labels:
                #         instr.args.labels[label_id] += len(basic_blocks) - _ + 1 + 1
                #     if instr.args.default is not None:
                #         instr.args.default += len(basic_blocks) - _ + 1 + 1

            # Wrap the instructions with block instruction
            basic_blocks[_] = Instruction(Block, BlockArgs(BlockTypeEmpty, bb))

        for _, bb in enumerate(basic_blocks):

            # Build next jump
            if code_blocks[_]['id'] == (len(code_blocks) - 1):
                param_type_list = block_type.param_types

                if param_type_list != [] and Collatz_func_id is not None:
                    jump_flag = len(code_blocks)
                    collatz_code = []

                    for param_id, param_type in enumerate(param_type_list):
                        if param_type == 127:
                            collatz_code.extend([
                                Instruction(LocalGet, param_id),
                                Instruction(I32Const, random.randint(1, 1000)),
                                Instruction(I32Mul)])
                        elif param_type == 126:
                            collatz_code.extend([
                                Instruction(LocalGet, param_id),
                                Instruction(I64Const, random.randint(1, 1000)),
                                Instruction(I64Mul),
                                Instruction(I32WrapI64)])
                        elif param_type == 125:
                            collatz_code.extend([
                                Instruction(LocalGet, param_id),
                                Instruction(F32Const, random.randint(1, 1000)),
                                Instruction(F32Mul),
                                Instruction(I32ReinterpretF32)])
                        elif param_type == 124:
                            collatz_code.extend([
                                Instruction(LocalGet, param_id),
                                Instruction(F64Const, random.randint(1, 1000)),
                                Instruction(F64Mul),
                                Instruction(I64ReinterpretF64),
                                Instruction(I32WrapI64)])
                        if param_id != 0:
                            collatz_code.append(Instruction(I32Add))

                    collatz_code.extend([
                        Instruction(I32Const, random.randint(1050, 2000)),
                        Instruction(I32Add),
                        Instruction(I32Const, random.randint(1, 2000)),
                        Instruction(Call, Collatz_func_id),
                        Instruction(I32Const, jump_flag - 1),
                        Instruction(I32Add),
                        Instruction(LocalSet, jump_flag_local),

                        # Jump to distribution block
                        Instruction(Br, len(code_blocks) - _),
                    ])
                    bb.args.instrs.extend(collatz_code)
                else:
                    bb.args.instrs.append(Instruction(I32Const, len(code_blocks)))
                    bb.args.instrs.append(Instruction(LocalSet, jump_flag_local))
                    bb.args.instrs.append(Instruction(Br, len(code_blocks) - _))
            else:
                for next_id, cb in enumerate(code_blocks):
                    if cb['id'] == (code_blocks[_]['id'] + 1):
                        param_type_list = block_type.param_types

                        if param_type_list != [] and Collatz_func_id is not None:
                            collatz_code = []
                            for param_id, param_type in enumerate(param_type_list):
                                if param_type == 127:
                                    collatz_code.extend([
                                        Instruction(LocalGet, param_id),
                                        Instruction(I32Const, random.randint(1, 1000)),
                                        Instruction(I32Mul)])
                                elif param_type == 126:
                                    collatz_code.extend([
                                        Instruction(LocalGet, param_id),
                                        Instruction(I64Const, random.randint(1, 1000)),
                                        Instruction(I64Mul),
                                        Instruction(I32WrapI64)])
                                elif param_type == 125:
                                    collatz_code.extend([
                                        Instruction(LocalGet, param_id),
                                        Instruction(F32Const, random.randint(1, 1000)),
                                        Instruction(F32Mul),
                                        Instruction(I32ReinterpretF32)])
                                elif param_type == 124:
                                    collatz_code.extend([
                                        Instruction(LocalGet, param_id),
                                        Instruction(F64Const, random.randint(1, 1000)),
                                        Instruction(F64Mul),
                                        Instruction(I64ReinterpretF64),
                                        Instruction(I32WrapI64)])
                                if param_id != 0:
                                    collatz_code.append(Instruction(I32Add))

                            if next_id == 0:
                                collatz_code.extend([
                                    Instruction(I32Const, random.randint(1050, 2000)),
                                    Instruction(I32Add),
                                    Instruction(I32Const, random.randint(1, 2000)),
                                    Instruction(Call, Collatz_func_id),
                                    Instruction(I32Const, 1),
                                    Instruction(I32Sub),
                                    Instruction(LocalSet, jump_flag_local),

                                    # Jump to distribution block
                                    Instruction(Br, len(basic_blocks) - _),
                                ])
                            elif next_id == 1:
                                collatz_code.extend([
                                    Instruction(I32Const, random.randint(1050, 2000)),
                                    Instruction(I32Add),
                                    Instruction(I32Const, random.randint(1, 2000)),
                                    Instruction(Call, Collatz_func_id),
                                    Instruction(LocalSet, jump_flag_local),

                                    # Jump to distribution block
                                    Instruction(Br, len(basic_blocks) - _),
                                ])
                            # jump flag = next id
                            else:
                                collatz_code.extend([
                                    Instruction(I32Const, random.randint(1050, 2000)),
                                    Instruction(I32Add),
                                    Instruction(I32Const, random.randint(1050, 2000)),
                                    Instruction(Call, Collatz_func_id),
                                    Instruction(I32Const, next_id - 1),
                                    Instruction(I32Add),
                                    Instruction(LocalSet, jump_flag_local),

                                    # Jump to distribution block
                                    Instruction(Br, len(basic_blocks) - _),
                                ])

                            bb.args.instrs.extend(collatz_code)
                        else:
                            bb.args.instrs.append(Instruction(I32Const, next_id))
                            bb.args.instrs.append(Instruction(LocalSet, jump_flag_local))
                            bb.args.instrs.append(Instruction(Br, len(basic_blocks) - _))

        # Construct outer blocks
        for _, bb in enumerate(basic_blocks):
            # Insert the distribution block at the beginning of the innermost block
            if _ == 0:
                bb.args.instrs.insert(0, dispatcher_block)
            else:
                bb.args.instrs.insert(0, basic_blocks[_ - 1])

        # Build loop block
        loop_block = Instruction(Loop, BlockArgs(BlockTypeEmpty, [basic_blocks[len(basic_blocks) - 1]]))

        loop_block.args.instrs.append(Instruction(Br, 1))

        # Build the outermost block
        out_block = Instruction(Block, BlockArgs(BlockTypeEmpty, []))

        # Find the first execution basic block as the entry point
        for _, cb in enumerate(code_blocks):
            if cb['id'] == 0:
                out_block.args.instrs.append(Instruction(I32Const, _))
                out_block.args.instrs.append(Instruction(LocalSet, jump_flag_local))

        # Add a dead branch guarded by an opaque parity predicate. For every
        # 32-bit value x, x * (x + 1) is even, including when arithmetic wraps,
        # so the branch body cannot run. Its runtime-dependent condition is
        # harder to discard by simple constant folding than an immediate 0.
        out_block.args.instrs.extend([
            Instruction(LocalGet, jump_flag_local),
            Instruction(LocalGet, jump_flag_local),
            Instruction(I32Const, 1),
            Instruction(I32Add),
            Instruction(I32Mul),
            Instruction(I32Const, 1),
            Instruction(I32And),
            Instruction(I32Const, 1),
            Instruction(I32Eq),
        ])
        bogus_body = [
            Instruction(I32Const, random.randint(-1000000, 1000000)),
            Instruction(I32Const, random.randint(-1000000, 1000000)),
            Instruction(I32Mul),
            Instruction(I32Const, random.randint(-1000000, 1000000)),
            Instruction(I32Add),
            Instruction(Drop),
        ]
        out_block.args.instrs.append(
            Instruction(If, IfArgs(BlockTypeEmpty, bogus_body))
        )
        out_block.args.instrs.append(loop_block)

        # Add operands at the end to maintain stack balance
        final_instrs = []
        final_instrs.append(out_block)

        if return_exist:
            for i, result_type in enumerate(
                    self.wasm_binary.module.type_sec[self.wasm_binary.module.func_sec[func_id]].result_types):
                if result_type == ValTypeI32:
                    final_instrs.append(Instruction(LocalGet, new_local_i32[i]))
                elif result_type == ValTypeI64:
                    final_instrs.append(Instruction(LocalGet, new_local_i64[i]))
                elif result_type == ValTypeF32:
                    final_instrs.append(Instruction(LocalGet, new_local_f32[i]))
                elif result_type == ValTypeF64:
                    final_instrs.append(Instruction(LocalGet, new_local_f64[i]))
                else:
                    raise Exception("error")

            final_instrs.append(Instruction(Return))
            return final_instrs
        else:
            for i, result_type in enumerate(
                    self.wasm_binary.module.type_sec[self.wasm_binary.module.func_sec[func_id]].result_types):
                if result_type == ValTypeI32:
                    final_instrs.append(Instruction(LocalGet, new_local_i32[i]))
                elif result_type == ValTypeI64:
                    final_instrs.append(Instruction(LocalGet, new_local_i64[i]))
                elif result_type == ValTypeF32:
                    final_instrs.append(Instruction(LocalGet, new_local_f32[i]))
                elif result_type == ValTypeF64:
                    final_instrs.append(Instruction(LocalGet, new_local_f64[i]))
                else:
                    raise Exception("error")
            return final_instrs

    def alias_disruption(self):
        if self.wasm_binary.module.table_sec_opaque:
            return

        func_ids = list(range(
            self.wasm_binary.get_import_func_num() + len(self.wasm_binary.module.func_sec)
        ))
        alias_table = self._append_alias_table(len(func_ids))
        random.shuffle(func_ids)
        alias_elem = Elem(alias_table, [Instruction(I32Const, 0)], func_ids)
        self.wasm_binary.module.elem_sec.append(alias_elem)
        self.alias_elem = alias_elem

        for _, func in enumerate(self.wasm_binary.module.code_sec):
            self.call_to_indirect_call(func.expr)

        # Modify the table segment, elem segment and code segment
        self.wasm_binary.modify_table_section(self.wasm_binary.module.table_sec)
        self.wasm_binary.modify_import_section(self.wasm_binary.module.import_sec)
        self.wasm_binary.modify_elem_section(self.wasm_binary.module.elem_sec)
        self.wasm_binary.modify_code_section(self.wasm_binary.module.code_sec)

    def call_to_indirect_call(self, expr):
        for _, instr in enumerate(expr):
            if instr.opcode == Call:
                # Get this function type id
                func_id = instr.args
                import_func_num = self.wasm_binary.get_import_func_num()
                if func_id <= (import_func_num - 1):
                    import_func_list = self.wasm_binary.get_import_func_list()
                    func_type_id = import_func_list[func_id].desc.func_type
                else:
                    func_type_id = self.wasm_binary.module.func_sec[func_id - self.wasm_binary.get_import_func_num()]
                # Normalize func_type_id to a type index (int) if needed
                norm: Optional[int] = self._ensure_type_index(func_type_id)
                if norm is None:
                    # unexpected type for func_type_id, skip transforming this call
                    continue
                func_type_id = norm

                # Build call_indirect instruction
                expr[_] = Instruction(
                    CallIndirect, CallIndirectArgs(func_type_id, self.alias_elem.table)
                )
                # Get the index of this function in funcref
                funcref_id = self.alias_elem.init.index(func_id) + self.alias_elem.offset[0].args
                # Push the funcref index on the stack
                expr.insert(_, Instruction(I32Const, funcref_id))

            # Recursive call
            elif instr.opcode in [Block, Loop]:
                self.call_to_indirect_call(instr.args.instrs)
            elif instr.opcode == If:
                self.call_to_indirect_call(instr.args.instrs1)
                self.call_to_indirect_call(instr.args.instrs2)

    def alias_disruption_collatz(self, Collatz_func_id):
        if self.wasm_binary.module.table_sec_opaque:
            return

        func_ids = list(range(
            self.wasm_binary.get_import_func_num() + len(self.wasm_binary.module.func_sec)
        ))
        alias_table = self._append_alias_table(len(func_ids))
        random.shuffle(func_ids)
        alias_elem = Elem(alias_table, [Instruction(I32Const, 0)], func_ids)
        self.wasm_binary.module.elem_sec.append(alias_elem)
        self.alias_elem = alias_elem

        collatz_code_index = Collatz_func_id - self.wasm_binary.get_import_func_num()
        for i, func in enumerate(self.wasm_binary.module.code_sec):
            if i != collatz_code_index:
                self.call_to_indirect_call_collatz(func.expr, Collatz_func_id)

        self.wasm_binary.modify_table_section(self.wasm_binary.module.table_sec)
        self.wasm_binary.modify_import_section(self.wasm_binary.module.import_sec)
        self.wasm_binary.modify_elem_section(self.wasm_binary.module.elem_sec)
        self.wasm_binary.modify_code_section(self.wasm_binary.module.code_sec)

    def call_to_indirect_call_collatz(self, expr, Collatz_func_id):
        _ = 0
        while _ < len(expr):
            if expr[_].opcode == Call:
                # Get this function type id
                func_id = expr[_].args
                import_func_num = self.wasm_binary.get_import_func_num()
                if func_id <= (import_func_num - 1):
                    func_type_id = self.wasm_binary.module.import_sec[func_id].desc.func_type
                else:
                    func_type_id = self.wasm_binary.module.func_sec[func_id - self.wasm_binary.get_import_func_num()]
                # Normalize func_type_id to a type index (int) if needed
                norm: Optional[int] = self._ensure_type_index(func_type_id)
                if norm is None:
                    _ += 1
                    continue
                func_type_id = norm

                # Build call_indirect instruction
                expr[_] = Instruction(
                    CallIndirect, CallIndirectArgs(func_type_id, self.alias_elem.table)
                )
                # Get the index of this function in funcref
                funcref_id = self.alias_elem.init.index(func_id) + self.alias_elem.offset[0].args
                # Keep the original call arguments on the stack, run the
                # Collatz helper on a fixed terminating input, then supply
                # the exact table index required by call_indirect.
                decoy = [
                    Instruction(I32Const, 32),
                    Instruction(I32Const, 0),
                    Instruction(Call, Collatz_func_id),
                    Instruction(Drop),
                    Instruction(I32Const, funcref_id),
                ]
                for instruction in reversed(decoy):
                    expr.insert(_, instruction)
                _ += len(decoy) + 1
            # Recursive call
            elif expr[_].opcode in [Block, Loop]:
                self.call_to_indirect_call_collatz(expr[_].args.instrs, Collatz_func_id)
                _ += 1
            elif expr[_].opcode == If:
                self.call_to_indirect_call_collatz(expr[_].args.instrs1, Collatz_func_id)
                self.call_to_indirect_call_collatz(expr[_].args.instrs2, Collatz_func_id)
                _ += 1
            else:
                _ += 1

    def _append_alias_table(self, size):
        imported_tables = sum(
            1 for item in self.wasm_binary.module.import_sec if item.desc.table is not None
        )
        table_index = imported_tables + len(self.wasm_binary.module.table_sec)
        self.wasm_binary.module.table_sec.append(
            TableType(elem_type=FuncRef, limits=Limits(0, size, 0))
        )
        return table_index

    def memory_encrypten_obfuscation(self, key=None):
        module = self.wasm_binary.module
        if key is None:
            key = random.randint(1, 255)
        if not isinstance(key, int) or not 0 < key < 256:
            raise ValueError("memory obfuscation key must be an integer from 1 to 255")

        # This representation stores every memory byte XORed with one byte.
        # Keep the transform conservative where host-visible memory or memory
        # operations outside the scalar/vector accesses below could observe or
        # modify the encoded representation directly.
        imported_memories = sum(1 for item in module.import_sec if item.desc.mem is not None)
        exported_memories = any(item.desc.tag == ExportTagMem for item in module.export_sec)
        if (imported_memories or exported_memories or len(module.mem_sec) != 1
                or module.mem_sec[0].tag & 0x06 or module.data_sec_opaque):
            return

        def walk(instrs):
            for instr in instrs:
                yield instr
                if instr.opcode in [Block, Loop]:
                    yield from walk(instr.args.instrs)
                elif instr.opcode == If:
                    yield from walk(instr.args.instrs1)
                    yield from walk(instr.args.instrs2)

        all_instructions = []
        for code in module.code_sec:
            if code.raw_body is not None:
                return
            all_instructions.extend(walk(code.expr))

        # memory.grow creates zero-filled bytes, while passive data and most
        # SIMD memory operators need their own encoding rules. Do not emit a
        # partially correct transform for those modules.
        unsupported_memory_ops = {MemoryGrow, MemoryInit}
        if any(instr.opcode in unsupported_memory_ops for instr in all_instructions):
            return
        if any(
            (V128Load <= instr.opcode <= V128Store
             and instr.opcode not in [V128Load, V128Store])
            or 0xFD54 <= instr.opcode <= 0xFD5D
            for instr in all_instructions
        ):
            return
        if not any(
            I32Load <= instr.opcode <= I64Store32
            or instr.opcode in [V128Load, V128Store]
            for instr in all_instructions
        ):
            return

        memory_bytes = module.mem_sec[0].min * 65536
        if memory_bytes > 0xFFFFFFFF:
            return
        data_ranges = []
        for data in module.data_sec:
            if data.mem != 0 or len(data.offset) != 1 or data.offset[0].opcode != I32Const:
                return
            start = data.offset[0].args & 0xFFFFFFFF
            end = start + len(data.init)
            if end > memory_bytes:
                return
            data_ranges.append((start, end))

        # Data segments are installed before the start function runs, so keep
        # their bytes encoded in the binary and initialize only the untouched
        # gaps to encoded zero. A constant byte key makes scalar width changes
        # and unaligned accesses use the same byte mask.
        for data in module.data_sec:
            data.init = bytes(byte ^ key for byte in data.init)

        merged_ranges = []
        for start, end in sorted(data_ranges):
            if start == end:
                continue
            if merged_ranges and start <= merged_ranges[-1][1]:
                merged_ranges[-1] = (merged_ranges[-1][0], max(end, merged_ranges[-1][1]))
            else:
                merged_ranges.append((start, end))

        initialization = []
        cursor = 0
        for start, end in merged_ranges:
            if cursor < start:
                initialization.extend([
                    Instruction(I32Const, cursor), Instruction(I32Const, 0),
                    Instruction(I32Const, start - cursor), Instruction(MemoryFill, 0),
                ])
            cursor = max(cursor, end)
        if cursor < memory_bytes:
            initialization.extend([
                Instruction(I32Const, cursor), Instruction(I32Const, 0),
                Instruction(I32Const, memory_bytes - cursor), Instruction(MemoryFill, 0),
            ])

        import_func_count = self.wasm_binary.get_import_func_num()
        start_func = module.start_sec
        if initialization:
            if start_func is not None and start_func >= import_func_count:
                module.code_sec[start_func - import_func_count].expr[0:0] = initialization
            else:
                start_expr = initialization[:]
                if start_func is not None:
                    start_expr.append(Instruction(Call, start_func))
                start_func = self.wasm_binary.add_function(
                    FuncType(param_types=[], result_types=[]), [], start_expr
                )
                module.start_sec = start_func

        i32_stores = {I32Store, I32Store8, I32Store16}
        i64_stores = {I64Store, I64Store8, I64Store16, I64Store32}
        f32_stores = {F32Store}
        f64_stores = {F64Store}
        i32_key = sum(key << (8 * byte) for byte in range(4))
        i64_key = sum(key << (8 * byte) for byte in range(8))
        v128_key = sum(key << (8 * byte) for byte in range(16))
        i32_key_signed = i32_key if i32_key < 0x80000000 else i32_key - 0x100000000
        i64_key_signed = i64_key if i64_key < 0x8000000000000000 else i64_key - 0x10000000000000000

        load_masks = {
            I32Load: (i32_key_signed, I32Xor, None),
            I32Load8S: (key, I32Xor, I32Extend8S),
            I32Load8U: (key, I32Xor, None),
            I32Load16S: (key * 0x0101, I32Xor, I32Extend16S),
            I32Load16U: (key * 0x0101, I32Xor, None),
            I64Load: (i64_key_signed, I64Xor, None),
            I64Load8S: (key, I64Xor, I64Extend8S),
            I64Load8U: (key, I64Xor, None),
            I64Load16S: (key * 0x0101, I64Xor, I64Extend16S),
            I64Load16U: (key * 0x0101, I64Xor, None),
            I64Load32S: (i32_key, I64Xor, I64Extend32S),
            I64Load32U: (i32_key, I64Xor, None),
        }
        store_masks = {
            I32Store: (i32_key_signed, I32Xor, None, None),
            I32Store8: (key, I32Xor, None, None),
            I32Store16: (key * 0x0101, I32Xor, None, None),
            I64Store: (i64_key_signed, I64Xor, None, None),
            I64Store8: (key, I64Xor, None, None),
            I64Store16: (key * 0x0101, I64Xor, None, None),
            I64Store32: (i32_key, I64Xor, None, None),
            F32Store: (i32_key_signed, I32Xor, None, I32ReinterpretF32),
            F64Store: (i64_key_signed, I64Xor, None, I64ReinterpretF64),
        }

        def rewrite(instrs, locals_by_type):
            rewritten = []
            for instr in instrs:
                if instr.opcode in [Block, Loop]:
                    instr.args.instrs = rewrite(instr.args.instrs, locals_by_type)
                elif instr.opcode == If:
                    instr.args.instrs1 = rewrite(instr.args.instrs1, locals_by_type)
                    instr.args.instrs2 = rewrite(instr.args.instrs2, locals_by_type)

                if instr.opcode in load_masks:
                    mask, xor_opcode, sign_extend = load_masks[instr.opcode]
                    # Signed narrow loads must sign-extend after decrypting the
                    # original byte(s), since ciphertext's sign bit differs.
                    load_opcode = instr.opcode
                    if instr.opcode == I32Load8S:
                        load_opcode = I32Load8U
                    elif instr.opcode == I32Load16S:
                        load_opcode = I32Load16U
                    elif instr.opcode == I64Load8S:
                        load_opcode = I64Load8U
                    elif instr.opcode == I64Load16S:
                        load_opcode = I64Load16U
                    elif instr.opcode == I64Load32S:
                        load_opcode = I64Load32U
                    rewritten.append(Instruction(load_opcode, instr.args))
                    rewritten.extend([
                        Instruction(I32Const if xor_opcode == I32Xor else I64Const, mask),
                        Instruction(xor_opcode),
                    ])
                    if sign_extend is not None:
                        rewritten.append(Instruction(sign_extend))
                elif instr.opcode in [F32Load, F64Load]:
                    rewritten.append(instr)
                    if instr.opcode == F32Load:
                        rewritten.extend([
                            Instruction(I32ReinterpretF32), Instruction(I32Const, i32_key_signed),
                            Instruction(I32Xor), Instruction(F32ReinterpretI32),
                        ])
                    else:
                        rewritten.extend([
                            Instruction(I64ReinterpretF64), Instruction(I64Const, i64_key_signed),
                            Instruction(I64Xor), Instruction(F64ReinterpretI64),
                        ])
                elif instr.opcode in store_masks:
                    mask, xor_opcode, _, reinterpret = store_masks[instr.opcode]
                    local_idx = locals_by_type[instr.opcode]
                    rewritten.append(Instruction(LocalSet, local_idx))
                    rewritten.append(Instruction(LocalGet, local_idx))
                    if reinterpret is not None:
                        rewritten.append(Instruction(reinterpret))
                    rewritten.append(Instruction(I32Const if xor_opcode == I32Xor else I64Const, mask))
                    rewritten.append(Instruction(xor_opcode))
                    if instr.opcode == F32Store:
                        rewritten.append(Instruction(F32ReinterpretI32))
                    elif instr.opcode == F64Store:
                        rewritten.append(Instruction(F64ReinterpretI64))
                    rewritten.append(instr)
                elif instr.opcode == V128Load:
                    rewritten.extend([
                        instr, Instruction(V128Const, v128_key), Instruction(V128Xor),
                    ])
                elif instr.opcode == V128Store:
                    local_idx = locals_by_type[V128Store]
                    rewritten.extend([
                        Instruction(LocalSet, local_idx),
                        Instruction(LocalGet, local_idx),
                        Instruction(V128Const, v128_key), Instruction(V128Xor), instr,
                    ])
                elif instr.opcode == MemoryFill:
                    dest_local, value_local, length_local = locals_by_type[MemoryFill]
                    rewritten.extend([
                        Instruction(LocalSet, length_local),
                        Instruction(LocalSet, value_local),
                        Instruction(LocalSet, dest_local),
                        Instruction(LocalGet, dest_local),
                        Instruction(LocalGet, value_local), Instruction(I32Const, key),
                        Instruction(I32Xor),
                        Instruction(LocalGet, length_local), instr,
                    ])
                else:
                    rewritten.append(instr)
            return rewritten

        for func_id, code in enumerate(module.code_sec):
            func_instrs = list(walk(code.expr))
            locals_by_type = {}
            for opcodes, local_type in [
                (i32_stores, ValTypeI32), (i64_stores, ValTypeI64),
                (f32_stores, ValTypeF32), (f64_stores, ValTypeF64),
            ]:
                if any(instr.opcode in opcodes for instr in func_instrs):
                    local_indices = {
                        I32Store: ValTypeI32, I32Store8: ValTypeI32, I32Store16: ValTypeI32,
                        I64Store: ValTypeI64, I64Store8: ValTypeI64, I64Store16: ValTypeI64,
                        I64Store32: ValTypeI64, F32Store: ValTypeF32, F64Store: ValTypeF64,
                    }
                    local_idx = self.wasm_binary.add_new_local_to_func(func_id, local_type)
                    for opcode in opcodes:
                        if opcode in local_indices:
                            locals_by_type[opcode] = local_idx
            if any(instr.opcode == V128Store for instr in func_instrs):
                locals_by_type[V128Store] = self.wasm_binary.add_new_local_to_func(func_id, ValTypeV128)
            if any(instr.opcode == MemoryFill for instr in func_instrs):
                locals_by_type[MemoryFill] = [
                    self.wasm_binary.add_new_local_to_func(func_id, ValTypeI32)
                    for _ in range(3)
                ]
            code.expr = rewrite(code.expr, locals_by_type)

    def hook_load_store_instr(self, instrs, decrypten_load_funcid, encrypten_store_funcid):
        for _, i in enumerate(instrs):
            if i.opcode in [Block, Loop]:
                self.hook_load_store_instr(i.args.instrs, decrypten_load_funcid, encrypten_store_funcid)
            elif i.opcode == If:
                self.hook_load_store_instr(i.args.instrs1, decrypten_load_funcid, encrypten_store_funcid)
                self.hook_load_store_instr(i.args.instrs2, decrypten_load_funcid, encrypten_store_funcid)
            else:
                match i.opcode:
                    case LoadInstr.I32Load.value:
                        offset = i.args.offset
                        signed = 2
                        length = random.randint(1, 100)
                        instrs.insert(_ + 1, Instruction(I32WrapI64))
                        instrs[_] = Instruction(Call, decrypten_load_funcid)
                        instrs.insert(_, Instruction(I32Const, length))
                        instrs.insert(_, Instruction(I32Const, signed))
                        instrs.insert(_, Instruction(I32Const, offset))
                        _ += 5
                    case LoadInstr.I64Load.value:
                        offset = i.args.offset
                        signed = 2
                        length = random.randint(1, 100)
                        instrs[_] = Instruction(Call, decrypten_load_funcid)
                        instrs.insert(_, Instruction(I32Const, length))
                        instrs.insert(_, Instruction(I32Const, signed))
                        instrs.insert(_, Instruction(I32Const, offset))
                        _ += 4
                    case LoadInstr.F32Load.value:
                        offset = i.args.offset
                        signed = 2
                        length = random.randint(1, 100)
                        instrs.insert(_ + 1, Instruction(F32ReinterpretI32))
                        instrs.insert(_ + 1, Instruction(I32WrapI64))
                        instrs[_] = Instruction(Call, decrypten_load_funcid)
                        instrs.insert(_, Instruction(I32Const, length))
                        instrs.insert(_, Instruction(I32Const, signed))
                        instrs.insert(_, Instruction(I32Const, offset))
                        _ += 6
                    case LoadInstr.F64Load.value:
                        offset = i.args.offset
                        signed = 2
                        length = random.randint(1, 100)
                        instrs.insert(_ + 1, Instruction(F64ReinterpretI64))
                        instrs[_] = Instruction(Call, decrypten_load_funcid)
                        instrs.insert(_, Instruction(I32Const, length))
                        instrs.insert(_, Instruction(I32Const, signed))
                        instrs.insert(_, Instruction(I32Const, offset))
                        _ += 5
                    case LoadInstr.I32Load8S.value:
                        offset = i.args.offset
                        signed = 1
                        length = 0
                        instrs.insert(_ + 1, Instruction(I32WrapI64))
                        instrs[_] = Instruction(Call, decrypten_load_funcid)
                        instrs.insert(_, Instruction(I32Const, length))
                        instrs.insert(_, Instruction(I32Const, signed))
                        instrs.insert(_, Instruction(I32Const, offset))
                        _ += 5
                    case LoadInstr.I32Load8U.value:
                        offset = i.args.offset
                        signed = 0
                        length = 0
                        instrs.insert(_ + 1, Instruction(I32WrapI64))
                        instrs[_] = Instruction(Call, decrypten_load_funcid)
                        instrs.insert(_, Instruction(I32Const, length))
                        instrs.insert(_, Instruction(I32Const, signed))
                        instrs.insert(_, Instruction(I32Const, offset))
                        _ += 5
                    case LoadInstr.I32Load16S.value:
                        offset = i.args.offset
                        signed = 1
                        length = 1
                        instrs.insert(_ + 1, Instruction(I32WrapI64))
                        instrs[_] = Instruction(Call, decrypten_load_funcid)
                        instrs.insert(_, Instruction(I32Const, length))
                        instrs.insert(_, Instruction(I32Const, signed))
                        instrs.insert(_, Instruction(I32Const, offset))
                        _ += 5
                    case LoadInstr.I32Load16U.value:
                        offset = i.args.offset
                        signed = 0
                        length = 1
                        instrs.insert(_ + 1, Instruction(I32WrapI64))
                        instrs[_] = Instruction(Call, decrypten_load_funcid)
                        instrs.insert(_, Instruction(I32Const, length))
                        instrs.insert(_, Instruction(I32Const, signed))
                        instrs.insert(_, Instruction(I32Const, offset))
                        _ += 5
                    case LoadInstr.I64Load8S.value:
                        offset = i.args.offset
                        signed = 1
                        length = 0
                        instrs[_] = Instruction(Call, decrypten_load_funcid)
                        instrs.insert(_, Instruction(I32Const, length))
                        instrs.insert(_, Instruction(I32Const, signed))
                        instrs.insert(_, Instruction(I32Const, offset))
                        _ += 4
                    case LoadInstr.I64Load8U.value:
                        offset = i.args.offset
                        signed = 0
                        length = 0
                        instrs[_] = Instruction(Call, decrypten_load_funcid)
                        instrs.insert(_, Instruction(I32Const, length))
                        instrs.insert(_, Instruction(I32Const, signed))
                        instrs.insert(_, Instruction(I32Const, offset))
                        _ += 4
                    case LoadInstr.I64Load16S.value:
                        offset = i.args.offset
                        signed = 1
                        length = 1
                        instrs[_] = Instruction(Call, decrypten_load_funcid)
                        instrs.insert(_, Instruction(I32Const, length))
                        instrs.insert(_, Instruction(I32Const, signed))
                        instrs.insert(_, Instruction(I32Const, offset))
                        _ += 4
                    case LoadInstr.I64Load16U.value:
                        offset = i.args.offset
                        signed = 0
                        length = 1
                        instrs[_] = Instruction(Call, decrypten_load_funcid)
                        instrs.insert(_, Instruction(I32Const, length))
                        instrs.insert(_, Instruction(I32Const, signed))
                        instrs.insert(_, Instruction(I32Const, offset))
                        _ += 4
                    case LoadInstr.I64Load32S.value:
                        offset = i.args.offset
                        signed = 1
                        length = 2
                        instrs[_] = Instruction(Call, decrypten_load_funcid)
                        instrs.insert(_, Instruction(I32Const, length))
                        instrs.insert(_, Instruction(I32Const, signed))
                        instrs.insert(_, Instruction(I32Const, offset))
                        _ += 4
                    case LoadInstr.I64Load32U.value:
                        offset = i.args.offset
                        signed = 0
                        length = 2
                        instrs[_] = Instruction(Call, decrypten_load_funcid)
                        instrs.insert(_, Instruction(I32Const, length))
                        instrs.insert(_, Instruction(I32Const, signed))
                        instrs.insert(_, Instruction(I32Const, offset))
                        _ += 4
                    # store
                    case StoreInstr.I32Store.value:
                        offset = i.args.offset
                        length = 2
                        instrs[_] = Instruction(Call, encrypten_store_funcid)
                        instrs.insert(_, Instruction(I32Const, length))
                        instrs.insert(_, Instruction(I32Const, offset))
                        instrs.insert(_, Instruction(I64ExtendI32U))
                        _ += 4
                    case StoreInstr.I64Store.value:
                        offset = i.args.offset
                        length = 3
                        instrs[_] = Instruction(Call, encrypten_store_funcid)
                        instrs.insert(_, Instruction(I32Const, length))
                        instrs.insert(_, Instruction(I32Const, offset))
                        _ += 3
                    case StoreInstr.F32Store.value:
                        offset = i.args.offset
                        length = 2
                        instrs[_] = Instruction(Call, encrypten_store_funcid)
                        instrs.insert(_, Instruction(I32Const, length))
                        instrs.insert(_, Instruction(I32Const, offset))
                        instrs.insert(_, Instruction(I64ExtendI32U))
                        instrs.insert(_, Instruction(I32ReinterpretF32))
                        _ += 5
                    case StoreInstr.F64Store.value:
                        offset = i.args.offset
                        length = 3
                        instrs[_] = Instruction(Call, encrypten_store_funcid)
                        instrs.insert(_, Instruction(I32Const, length))
                        instrs.insert(_, Instruction(I32Const, offset))
                        instrs.insert(_, Instruction(I64ReinterpretF64))
                        _ += 4
                    case StoreInstr.I32Store8.value:
                        offset = i.args.offset
                        length = 0
                        instrs[_] = Instruction(Call, encrypten_store_funcid)
                        instrs.insert(_, Instruction(I32Const, length))
                        instrs.insert(_, Instruction(I32Const, offset))
                        instrs.insert(_, Instruction(I64ExtendI32U))
                        _ += 4
                    case StoreInstr.I32Store16.value:
                        offset = i.args.offset
                        length = 1
                        instrs[_] = Instruction(Call, encrypten_store_funcid)
                        instrs.insert(_, Instruction(I32Const, length))
                        instrs.insert(_, Instruction(I32Const, offset))
                        instrs.insert(_, Instruction(I64ExtendI32U))
                        _ += 4
                    case StoreInstr.I64Store8.value:
                        offset = i.args.offset
                        length = 0
                        instrs[_] = Instruction(Call, encrypten_store_funcid)
                        instrs.insert(_, Instruction(I32Const, length))
                        instrs.insert(_, Instruction(I32Const, offset))
                        _ += 3
                    case StoreInstr.I64Store16.value:
                        offset = i.args.offset
                        length = 1
                        instrs[_] = Instruction(Call, encrypten_store_funcid)
                        instrs.insert(_, Instruction(I32Const, length))
                        instrs.insert(_, Instruction(I32Const, offset))
                        _ += 3
                    case StoreInstr.I64Store32.value:
                        offset = i.args.offset
                        length = 2
                        instrs[_] = Instruction(Call, encrypten_store_funcid)
                        instrs.insert(_, Instruction(I32Const, length))
                        instrs.insert(_, Instruction(I32Const, offset))
                        _ += 3
                    case _:
                        _ += 1
