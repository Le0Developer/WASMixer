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

        if self.wasm_binary.module.data_sec == [] or self.wasm_binary.module.data_sec_opaque:
            return

        if key is None:
            key = random.randint(1, 128)

        segments = []
        for data in self.wasm_binary.module.data_sec:
            if data.mem != 0 or len(data.offset) != 1 or data.offset[0].opcode != I32Const:
                return
            start = data.offset[0].args
            if start < 0 or start + len(data.init) > 0x7FFFFFFF:
                return
            segments.append((start, data.init))

        # Encrypt each active data segment in the file. A tiny start function
        # decrypts it after data initialization and before the module's own
        # start function, leaving normal loads and stores untouched at runtime.
        for _, memory_data in segments:
            for index, byte in enumerate(memory_data):
                memory_data[index] = byte ^ key

        decrypt_expr = []
        for start, memory_data in segments:
            end = start + len(memory_data)
            decrypt_expr.extend([
                Instruction(I32Const, start),
                Instruction(LocalSet, 0),
                Instruction(Block, BlockArgs(BlockTypeEmpty, [
                    Instruction(Loop, BlockArgs(BlockTypeEmpty, [
                        Instruction(LocalGet, 0),
                        Instruction(I32Const, end),
                        Instruction(I32GeU),
                        Instruction(BrIf, 1),
                        Instruction(LocalGet, 0),
                        Instruction(LocalGet, 0),
                        Instruction(I32Load8U, MemArg()),
                        Instruction(I32Const, key),
                        Instruction(I32Xor),
                        Instruction(I32Store8, MemArg()),
                        Instruction(LocalGet, 0),
                        Instruction(I32Const, 1),
                        Instruction(I32Add),
                        Instruction(LocalSet, 0),
                        Instruction(Br, 0),
                    ])),
                ])),
            ])

        if self.wasm_binary.module.start_sec is not None:
            decrypt_expr.append(Instruction(Call, self.wasm_binary.module.start_sec))

        decrypt_type = FuncType(param_types=[], result_types=[])
        decrypt_func_id = self.wasm_binary.add_function(
            decrypt_type,
            [Locals(1, ValTypeI32)],
            decrypt_expr,
        )
        self.wasm_binary.module.start_sec = decrypt_func_id
        self.wasm_binary.modify_start_section(decrypt_func_id)
        self.wasm_binary.emit_binary()

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
