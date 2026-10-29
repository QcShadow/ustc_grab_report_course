#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Launch the local GUI: python gui.py"""

import warnings

warnings.filterwarnings("ignore")

from ustc_grab.gui.server import main


if __name__ == "__main__":
    raise SystemExit(main())
