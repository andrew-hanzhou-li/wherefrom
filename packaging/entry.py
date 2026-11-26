# What PyInstaller runs: the same as "python -m wherefrom".
import sys

from wherefrom.cli import main

sys.exit(main())
