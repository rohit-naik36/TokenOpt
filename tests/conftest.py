import os
import sys

# Move to the project root so that `from tokenopt_proxy_v2 import ...`
# (and sibling module imports) resolve regardless of the CWD pytest is run from.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
