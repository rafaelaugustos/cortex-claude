"""Multifile, refactoring and handoff fixtures with independent behavioral graders."""

CASES = [
    {
        "name": "money-multifile-v1",
        "buggy": {
            "money.py": 'def cents(value):\n    return round(float(value) * 100)\n',
            "cart.py": 'from money import cents\ndef total(items):\n    return cents(sum(float(item["price"]) * item["quantity"] for item in items))\n',
            "invoice.py": 'from cart import total\ndef invoice(items):\n    return {"currency": "BRL", "total_cents": total(items)}\n',
        },
        "fixed": {
            "money.py": 'from decimal import Decimal, ROUND_HALF_UP\ndef cents(value):\n    return int((Decimal(str(value)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))\n',
            "cart.py": 'from money import cents\ndef total(items):\n    return sum(cents(item["price"]) * item["quantity"] for item in items)\n',
            "invoice.py": 'from cart import total\ndef invoice(items):\n    return {"currency": "BRL", "total_cents": total(items)}\n',
        },
        "tests": '''import unittest
from money import cents
from cart import total
from invoice import invoice
class Checks(unittest.TestCase):
 def test_rounding(self):
  for value, expected in [("1.005",101),("2.675",268),("-1.005",-101),("0.105",11)]:
   with self.subTest(value=value): self.assertEqual(cents(value),expected)
 def test_unit_rounding_before_quantity(self):
  self.assertEqual(total([{"price":"0.105","quantity":3},{"price":"1.005","quantity":2}]),235)
 def test_invoice_and_empty(self):
  self.assertEqual(invoice([]),{"currency":"BRL","total_cents":0})
  self.assertEqual(invoice([{"price":"1.005","quantity":2}])["total_cents"],202)
''',
        "prompt": "Fix monetary precision across money.py, cart.py and invoice.py. Convert decimal prices to integer cents with ROUND_HALF_UP (including negative half ties), round each unit price before multiplying quantity, and preserve public APIs and invoice currency. Run python -m unittest -q.",
        "lesson": "For currency, Decimal(str(value)) avoids binary-float drift. Quantize to integer cents with ROUND_HALF_UP before multiplying each unit by quantity; summing floats before rounding changes invoice totals.",
        "cause": "Binary floating point and rounding totals instead of unit prices",
        "solution": "Centralize cents conversion with Decimal and multiply rounded unit cents",
        "triggers": "monetary precision money currency cents round quantity invoice",
    },
    {
        "name": "parser-refactor-v1",
        "buggy": {
            "flags.py": 'def parse_flag(value):\n    return bool(value)\n',
            "api.py": 'def api_enabled(config):\n    return config.get("enabled", "").lower() == "true"\n',
            "worker.py": 'def worker_enabled(config):\n    return config.get("enabled") == "1"\n',
        },
        "fixed": {
            "flags.py": 'def parse_flag(value):\n    return str(value).strip().casefold() in {"1","true","yes","on"}\n',
            "api.py": 'from flags import parse_flag\ndef api_enabled(config):\n    return parse_flag(config.get("enabled"))\n',
            "worker.py": 'from flags import parse_flag\ndef worker_enabled(config):\n    return parse_flag(config.get("enabled"))\n',
        },
        "tests": '''import unittest
from unittest.mock import patch
import flags, api, worker
class Checks(unittest.TestCase):
 def test_shared_semantics(self):
  for value in [None,"false","off","0","","invalid"]:
   self.assertFalse(flags.parse_flag(value))
   self.assertFalse(api.api_enabled({"enabled":value}))
   self.assertFalse(worker.worker_enabled({"enabled":value}))
  for value in ["1","true","ON"," yes "]:
   self.assertTrue(api.api_enabled({"enabled":value}))
   self.assertTrue(worker.worker_enabled({"enabled":value}))
 def test_missing(self):
  self.assertFalse(api.api_enabled({})); self.assertFalse(worker.worker_enabled({}))
 def test_delegation_not_duplicate_logic(self):
  sentinel = object()
  for module, name in [(api,"api_enabled"),(worker,"worker_enabled")]:
   with patch.object(flags,"parse_flag",return_value=sentinel), patch.object(module,"parse_flag",return_value=sentinel,create=True):
    self.assertIs(getattr(module,name)({"enabled":"not-standard"}),sentinel)
''',
        "prompt": "Refactor api.py and worker.py to delegate flag parsing to flags.parse_flag. Preserve APIs. Accept only 1/true/yes/on case-insensitively with whitespace stripped; None, missing and every other value disable it. Both callers must use the shared helper, with no duplicate parsing logic. Run python -m unittest -q.",
        "lesson": "When unifying flag parsers, change both callers to delegate to the shared helper. Normalize with str(value).strip().casefold() and check the explicit true-value set; verify delegation as well as behavior.",
        "cause": "Independent parsers disagreed on truthy values and None",
        "solution": "Normalize in one helper, import it in both consumers, test delegation and edge cases",
        "triggers": "refactor flag parsing shared helper callers api worker",
    },
    {
        "name": "resume-expiry-v1",
        "buggy": {
            "clock_units.py": 'def seconds(record):\n    value = record["expires_at"]\n    return value / 1000 if record.get("unit", "seconds") == "milliseconds" else value\n',
            "cache.py": 'def active(records, now):\n    return [r for r in records if now < r["expires_at"]]\n',
            "cleanup.py": 'def expired_ids(records, now):\n    return [r["id"] for r in records if now > r["expires_at"]]\n',
            "HANDOFF.md": 'Objective: consistent expiry across cache and cleanup.\nDone: clock_units.seconds converts declared milliseconds.\nDecision: missing unit means seconds; equality is expired.\nPending: wire both consumers to seconds; keep record order and avoid mutations.\nNext: update cache.py and cleanup.py, then run tests.\n',
        },
        "fixed": {
            "clock_units.py": 'def seconds(record):\n    value = record["expires_at"]\n    return value / 1000 if record.get("unit", "seconds") == "milliseconds" else value\n',
            "cache.py": 'from clock_units import seconds\ndef active(records, now):\n    return [r for r in records if now < seconds(r)]\n',
            "cleanup.py": 'from clock_units import seconds\ndef expired_ids(records, now):\n    return [r["id"] for r in records if now >= seconds(r)]\n',
        },
        "tests": '''import copy, unittest
from cache import active
from cleanup import expired_ids
class Checks(unittest.TestCase):
 def test_mixed_and_boundary(self):
  records = [{"id":"a","expires_at":10000,"unit":"milliseconds"},{"id":"b","expires_at":11},{"id":"c","expires_at":9}]
  original=copy.deepcopy(records)
  self.assertEqual([r["id"] for r in active(records,10)],["b"])
  self.assertEqual(expired_ids(records,10),["a","c"])
  self.assertEqual(records,original)
 def test_empty_and_future(self):
  self.assertEqual(active([],1),[]); self.assertEqual(expired_ids([],1),[])
  self.assertEqual(expired_ids([{"id":"future","expires_at":5000,"unit":"milliseconds"}],4),[])
''',
        "prompt": "Resume the expiry consistency task from HANDOFF.md. Complete the remaining work in cache.py and cleanup.py using clock_units.seconds. now is always seconds; equality is expired; retain order and do not mutate records. Preserve APIs. Run python -m unittest -q.",
        "lesson": "Use the existing seconds converter for both active-cache filtering and expired cleanup. Treat equality as expired, preserve order and avoid mutating stored records.",
        "cause": "A handoff migrated the converter but left two callers using raw timestamps",
        "solution": "Wire both consumers to seconds and use complementary < and >= comparisons",
        "triggers": "resume expiry cache cleanup handoff seconds",
        "checkpoint": {"title": "Expiry consistency", "summary": "clock_units.seconds is implemented; cache and cleanup still use raw timestamps", "decisions": ["Missing unit means seconds", "Equality is expired"], "pending": ["Update cache.py and cleanup.py", "Preserve order and records"], "next_step": "Wire both consumers to seconds and run python -m unittest -q", "dependencies": ["clock_units.py", "cache.py", "cleanup.py"]},
    },
]
