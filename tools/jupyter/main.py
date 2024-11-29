import os
import re
import sys

from notebook.app import main

if __name__ == "__main__":
    if "BUILD_WORKSPACE_DIRECTORY" in os.environ:
        os.chdir(os.environ["BUILD_WORKSPACE_DIRECTORY"])
    sys.argv[0] = re.sub(r"(-script\.pyw?|\.exe)?$", "", sys.argv[0])
    sys.argv.append("--NotebookApp.token=''")
    sys.argv.append("--no-browser")
    sys.exit(main())
