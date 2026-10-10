"""The Chrome debugger build is gone. The site flags that kind of access.

This starts the screen reader instead: it only looks at pixels you can already see.
"""

from screen_solver import main

if __name__ == "__main__":
    main()
