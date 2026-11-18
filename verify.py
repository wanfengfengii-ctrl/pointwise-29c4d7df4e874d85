"""Single entry point for the full verification chain.

Runs every unittest module (all original regressions plus the review-plan
suite), the V1 business witnesses and the independent review-plan audit.
A non-zero exit code propagates as soon as any check fails.
"""
import sys
import unittest

from review_cases import audit_persistence, audit_verdicts, check_sources


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.discover('tests')
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    if not result.wasSuccessful():
        return 1
    check_sources()
    audit_verdicts()
    audit_persistence()
    print('review_cases witnesses and audit ledger: OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
