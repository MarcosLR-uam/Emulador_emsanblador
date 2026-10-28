import unittest

from emulator import Emulator, EmulatorError, MAX_STEPS, parse
from app import app


class ArithmeticTests(unittest.TestCase):
    def test_all_arithmetic_inputs(self):
        for op in ("ADD", "SUB", "CMP"):
            for left in range(4):
                for right in range(4):
                    with self.subTest(op=op, left=left, right=right):
                        result = Emulator(f"MOV A, {left}\n{op} A, {right}").execute()
                        raw = left + right if op == "ADD" else left - right
                        signed_left = (0, 1, -2, -1)[left]
                        signed_right = (0, 1, -2, -1)[right]
                        signed_raw = signed_left + signed_right if op == "ADD" else signed_left - signed_right
                        self.assertEqual(result["registers"]["A"], left if op == "CMP" else raw % 4)
                        self.assertEqual(result["flags"], {
                            "ZF": int(raw % 4 == 0), "SF": int(raw % 4 >= 2),
                            "CF": int(raw > 3) if op == "ADD" else int(left < right),
                            "OF": int(signed_raw < -2 or signed_raw > 1)})

    def test_logic_all_inputs(self):
        for op, operation in (("AND", lambda left, right: left & right),
                              ("OR", lambda left, right: left | right),
                              ("XOR", lambda left, right: left ^ right)):
            for left in range(4):
                for right in range(4):
                    with self.subTest(op=op, left=left, right=right):
                        result = Emulator(f"MOV B, 3\nADD B, 1\nMOV A, {left}\n{op} A, {right}").execute()
                        expected = operation(left, right)
                        self.assertEqual(result["registers"]["A"], expected)
                        self.assertEqual(result["flags"], {"ZF": int(expected == 0), "SF": int(expected >= 2), "CF": 0, "OF": 0})

    def test_inc_dec_preserve_carry(self):
        for op in ("INC", "DEC"):
            for carry in (0, 1):
                for value in range(4):
                    with self.subTest(op=op, carry=carry, value=value):
                        prefix = "MOV B, 3\nADD B, 1\n" if carry else ""
                        result = Emulator(f"{prefix}MOV A, {value}\n{op} A").execute()
                        expected = (value + (1 if op == "INC" else -1)) % 4
                        self.assertEqual(result["registers"]["A"], expected)
                        self.assertEqual(result["flags"], {"CF": carry, "ZF": int(expected == 0),
                                                          "SF": int(expected >= 2), "OF": int(value == (1 if op == "INC" else 2))})

    def test_mov_preserves_flags_and_signed_binary_literals(self):
        result = Emulator("MOV A, 3\nADD A, 1\nMOV B, -2\nMOV A, B").execute()
        self.assertEqual(result["registers"], {"A": 2, "B": 2})
        self.assertEqual(result["flags"], {"ZF": 1, "CF": 1, "SF": 0, "OF": 0})
        self.assertEqual(Emulator("MOV A, 0b11").execute()["registers"]["A"], 3)


class ExecutionTests(unittest.TestCase):
    def test_conditional_jumps_all_pairs(self):
        for left in range(4):
            for right in range(4):
                conditions = {"JC": left < right, "JE": left == right, "JNE": left != right,
                              "JGE": (0, 1, -2, -1)[left] >= (0, 1, -2, -1)[right]}
                for op, taken in conditions.items():
                    with self.subTest(op=op, left=left, right=right):
                        result = Emulator(f"MOV A, {left}\nCMP A, {right}\n{op} yes\nMOV B, 1\nJMP end\nyes: MOV B, 2\nend: HLT").execute()
                        self.assertEqual(result["registers"]["B"], 2 if taken else 1)

    def test_loop_history_and_stepping(self):
        source = "; demo\nMOV B, 3\nloop: INC A\nDEC B\nCMP B, 0\nJNE loop\nHLT"
        cpu = Emulator(source)
        first = cpu.execute(1)
        self.assertEqual(first["next_line"], 3)
        cpu.execute(1)
        self.assertEqual(first["registers"]["A"], 0)
        complete = Emulator(source).execute()
        for count in range(complete["steps"] + 1):
            partial = Emulator(source).execute(count)
            self.assertEqual(partial["history"], complete["history"][:count])
        self.assertEqual(complete["registers"], {"A": 3, "B": 0})
        self.assertTrue(complete["halted"])

    def test_halt_end_label_case_and_comments(self):
        result = Emulator("mov a, 1 ; comentario\nhlt\nmov a, 2").execute()
        self.assertEqual(result["registers"]["A"], 1)
        self.assertEqual(result["steps"], 2)
        self.assertTrue(Emulator("JMP fin\nMOV A, 2\nfin:").execute()["halted"])

    def test_bounded_infinite_loop(self):
        cpu = Emulator("loop: JMP loop")
        result = cpu.execute()
        self.assertEqual(result["steps"], MAX_STEPS)
        self.assertTrue(result["limit_reached"])
        self.assertFalse(result["halted"])
        with self.assertRaises(EmulatorError):
            cpu.step()

    def test_invalid_programs(self):
        for source in (None, "", "; vacío", "NOP", "MOV C, 1", "MOV A 1", "MOV A, 4",
                       "MOV A, -3", "MOV A, foo", "ADD A,", "HLT 1", "JMP missing",
                       "same: HLT\nsame: HLT", "bad-label: HLT", "x" * 20001,
                       "INC A\n" * 501):
            with self.subTest(source=str(source)[:40]), self.assertRaises(EmulatorError):
                parse(source)
        for count in (-1, 2001, True, 1.5, "1", None):
            with self.subTest(count=count), self.assertRaises(EmulatorError):
                Emulator("HLT").execute(count)


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_page_health_and_api(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/health").json, {"status": "ok"})
        response = self.client.post("/api/execute", json={"code": "MOV A, 2\nINC A\nHLT", "steps": 1})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["registers"]["A"], 2)
        self.assertFalse(response.json["halted"])
        self.assertEqual(self.client.post("/api/execute", json={"code": "HLT"}).json["registers"]["A"], 0)

    def test_errors_and_limits(self):
        for payload in ([], None, {}, {"code": "BAD"}, {"code": "HLT", "steps": True}):
            response = self.client.post("/api/execute", json=payload)
            self.assertEqual(response.status_code, 400)
            self.assertIn("error", response.json)
        response = self.client.post("/api/execute", data="{", content_type="application/json")
        self.assertEqual(response.status_code, 400)
        response = self.client.post("/api/execute", data="x" * 100001, content_type="application/json")
        self.assertEqual(response.status_code, 413)
        self.assertIn("error", response.json)
        self.assertEqual(self.client.get("/api/execute").status_code, 405)


if __name__ == "__main__":
    unittest.main()
