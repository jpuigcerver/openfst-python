from __future__ import absolute_import
from __future__ import print_function

import unittest

import openfst_python as fst


class TestOpenFstPython(unittest.TestCase):
    def test_simple(self):
        f = fst.Fst()
        s0 = f.add_state()
        s1 = f.add_state()
        s2 = f.add_state()
        f.add_arc(s0, fst.Arc(1, 1, fst.Weight(f.weight_type(), 3.0), s1))
        f.add_arc(s0, fst.Arc(1, 1, fst.Weight.One(f.weight_type()), s2))
        f.set_start(s0)
        f.set_final(s2, fst.Weight(f.weight_type(), 1.5))
        # Test fst
        self.assertEqual(f.num_states(), 3)
        self.assertAlmostEqual(float(f.final(s2)), 1.5)

    def test_compile(self):
        compiler = fst.Compiler()
        print("0 1 97 120 .5", file=compiler)
        print("0 1 98 121 1.5", file=compiler)
        print("1 2 99 123 2.5", file=compiler)
        print("2 3.5", file=compiler)
        f = compiler.compile()
        # Test fst
        self.assertEqual(f.num_states(), 3)
        self.assertAlmostEqual(float(f.final(2)), 3.5)


if __name__ == "__main__":
    unittest.main()
