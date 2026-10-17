"""Execute actual economy implementation against temporary SQLite databases."""
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]

class EconomyTests(unittest.TestCase):
    def test_real_cpp_ledger_rewards_and_retry(self):
        with tempfile.TemporaryDirectory() as d:
            binary=Path(d)/'economy'
            subprocess.run(['g++','-std=c++14','-Wall','-Wextra','-Werror','-pedantic',
                str(ROOT/'baseline/competitive/economy.cpp'),str(ROOT/'baseline/competitive/economy_tests.cpp'),
                '-lsqlite3','-o',str(binary)],check=True)
            subprocess.run([str(binary),d],check=True)

if __name__=='__main__':unittest.main()