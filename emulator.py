"""CPU educativa de 2 bits con ejecución determinista y acotada."""

from dataclasses import dataclass
import re

MAX_STEPS = 2000
MAX_SOURCE = 20000
MAX_INSTRUCTIONS = 500
REGISTERS = {"A", "B"}
ARITY = {**dict.fromkeys(("MOV", "CMP", "ADD", "SUB", "AND", "OR", "XOR"), 2),
         **dict.fromkeys(("JC", "JGE", "JMP", "JE", "JNE", "INC", "DEC"), 1), "HLT": 0}
JUMPS = {"JC", "JGE", "JMP", "JE", "JNE"}


class EmulatorError(ValueError):
    """Error de sintaxis o límite del programa."""


@dataclass(frozen=True)
class Instruction:
    op: str
    args: tuple
    line: int
    text: str


def immediate(token):
    try:
        value = int(token, 2 if token.lower().startswith("0b") else 10)
    except ValueError as exc:
        raise EmulatorError(f"Operando inválido: {token}.") from exc
    if not -2 <= value <= 3:
        raise EmulatorError("Los inmediatos deben estar entre -2 y 3 (o 0b00 a 0b11).")
    return value & 3


def parse(source):
    if not isinstance(source, str) or len(source) > MAX_SOURCE:
        raise EmulatorError(f"El código debe ser texto de hasta {MAX_SOURCE} caracteres.")
    instructions, labels = [], {}
    for line_number, raw in enumerate(source.splitlines(), 1):
        text = raw.split(";", 1)[0].strip().upper()
        if not text:
            continue
        match = re.match(r"^([A-Z_][A-Z_0-9]*)\s*:\s*(.*)$", text)
        if match:
            label, text = match.groups()
            if label in labels:
                raise EmulatorError(f"Línea {line_number}: etiqueta repetida {label}.")
            labels[label] = len(instructions)
        if not text:
            continue
        pieces = text.split(maxsplit=1)
        op = pieces[0]
        if op not in ARITY:
            raise EmulatorError(f"Línea {line_number}: instrucción desconocida {op}.")
        args = tuple(part.strip() for part in pieces[1].split(",")) if len(pieces) == 2 else ()
        if len(args) != ARITY[op] or any(not arg for arg in args):
            raise EmulatorError(f"Línea {line_number}: {op} requiere {ARITY[op]} operandos separados por coma.")
        if op not in JUMPS and args:
            if args[0] not in REGISTERS:
                raise EmulatorError(f"Línea {line_number}: el destino debe ser A o B.")
            if len(args) == 2 and args[1] not in REGISTERS:
                try:
                    immediate(args[1])
                except EmulatorError as exc:
                    raise EmulatorError(f"Línea {line_number}: {exc}") from exc
        instructions.append(Instruction(op, args, line_number, text))
        if len(instructions) > MAX_INSTRUCTIONS:
            raise EmulatorError(f"Máximo {MAX_INSTRUCTIONS} instrucciones.")
    if not instructions:
        raise EmulatorError("Escribí al menos una instrucción.")
    for instruction in instructions:
        if instruction.op in JUMPS and instruction.args[0] not in labels:
            raise EmulatorError(f"Línea {instruction.line}: etiqueta inexistente {instruction.args[0]}.")
    return instructions, labels


def signed(value):
    return value if value < 2 else value - 4


class Emulator:
    def __init__(self, source):
        self.instructions, self.labels = parse(source)
        self.registers = {"A": 0, "B": 0}
        self.flags = dict.fromkeys(("ZF", "CF", "SF", "OF"), 0)
        self.pc = 0
        self.halted = False
        self.history = []

    def snapshot(self):
        return {"registers": self.registers.copy(), "flags": self.flags.copy(),
                "pc": self.pc, "halted": self.halted}

    def arithmetic(self, left, right, subtract=False, preserve_carry=False):
        previous_carry = self.flags["CF"]
        raw = left - right if subtract else left + right
        result = raw & 3
        signed_result = signed(left) - signed(right) if subtract else signed(left) + signed(right)
        self.flags.update(ZF=int(result == 0), SF=int(bool(result & 2)),
                          CF=int(left < right) if subtract else int(raw > 3),
                          OF=int(not -2 <= signed_result <= 1))
        if preserve_carry:
            self.flags["CF"] = previous_carry
        return result

    def step(self):
        if self.halted:
            return
        if len(self.history) >= MAX_STEPS:
            raise EmulatorError(f"Límite de {MAX_STEPS} pasos alcanzado; revisá los bucles.")
        instruction = self.instructions[self.pc]
        before = self.snapshot()
        op, args = instruction.op, instruction.args
        self.pc += 1
        if op in JUMPS:
            taken = {"JMP": True, "JC": self.flags["CF"] == 1,
                     "JGE": self.flags["SF"] == self.flags["OF"],
                     "JE": self.flags["ZF"] == 1, "JNE": self.flags["ZF"] == 0}[op]
            if taken:
                self.pc = self.labels[args[0]]
        elif op == "HLT":
            self.halted = True
        else:
            destination = args[0]
            left = self.registers[destination]
            right = (self.registers[args[1]] if args[1] in REGISTERS else immediate(args[1])) if len(args) == 2 else 1
            if op == "MOV":
                self.registers[destination] = right
            elif op in {"ADD", "SUB", "CMP", "INC", "DEC"}:
                result = self.arithmetic(left, right, op in {"SUB", "CMP", "DEC"}, op in {"INC", "DEC"})
                if op != "CMP":
                    self.registers[destination] = result
            else:
                result = {"AND": left & right, "OR": left | right, "XOR": left ^ right}[op]
                self.registers[destination] = result
                self.flags.update(ZF=int(result == 0), SF=int(bool(result & 2)), CF=0, OF=0)
        if self.pc == len(self.instructions):
            self.halted = True
        self.history.append({"step": len(self.history) + 1, "line": instruction.line,
                             "instruction": instruction.text, "before": before, "after": self.snapshot()})

    def execute(self, steps=MAX_STEPS):
        if type(steps) is not int or not 0 <= steps <= MAX_STEPS:
            raise EmulatorError(f"Los pasos deben ser un entero entre 0 y {MAX_STEPS}.")
        for _ in range(steps):
            if self.halted:
                break
            self.step()
        result = self.snapshot()
        result.update(history=self.history, steps=len(self.history),
                      limit_reached=not self.halted and len(self.history) == MAX_STEPS,
                      next_line=None if self.halted else self.instructions[self.pc].line,
                      program=[{"line": item.line, "text": item.text} for item in self.instructions])
        return result
