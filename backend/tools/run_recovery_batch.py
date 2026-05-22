#!/usr/bin/env python3
import os
import sys


def main():
    # Allow running recovery_batch directly without manage.py shell quoting issues.
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    if '/app' not in sys.path:
        sys.path.insert(0, '/app')

    import django
    django.setup()

    from tools.recovery_batch import main as recovery_main

    ids = sys.argv[1:]
    if not ids:
        print('Usage: run_recovery_batch.py <session_id> [session_id ...]')
        return 1

    return recovery_main(ids)


if __name__ == '__main__':
    raise SystemExit(main())
