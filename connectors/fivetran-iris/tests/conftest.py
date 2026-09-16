import sys
from pathlib import Path

# Allow `import iris_connector` / `import connector` when pytest is run from
# any working directory, without installing this project as a package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
