"""Regression tests for the cross-dimension size matcher.

Run with: python -m pytest test_sizing.py -q
"""

from sizing import Match, PantsTarget, ShirtTarget

pants = PantsTarget(waist_in=35, inseam_in=34)
shirt = ShirtTarget(letter="L")


def test_pants_exact_inches():
    assert pants.match("W35").level is Match.EXACT
    assert pants.match("W35 L34").level is Match.EXACT
    assert pants.match("35x34").level is Match.EXACT
    assert pants.match("35").level is Match.EXACT


def test_pants_vinted_dual_notation():
    # Vinted renders men's pants sizes as "W34 | FR 44"
    assert pants.match("W35 | FR 45").level is Match.EXACT
    assert pants.match("W34 | FR 44").level is Match.CLOSE


def test_pants_fr_equivalent():
    assert pants.match("FR 45").level is Match.EQUIVALENT
    assert pants.match("45").level is Match.EQUIVALENT
    assert pants.match("44").level is Match.CLOSE
    assert pants.match("46").level is Match.CLOSE


def test_pants_it_equivalent():
    assert pants.match("IT 51").level is Match.EQUIVALENT
    assert pants.match("51").level is Match.EQUIVALENT
    assert pants.match("50").level is Match.CLOSE


def test_pants_letter():
    assert pants.match("L").level is Match.EQUIVALENT
    assert pants.match("M").level is Match.NONE


def test_pants_rejects():
    assert not pants.match("W32 | FR 42")
    assert not pants.match("XS")
    assert not pants.match("W35 L28")  # inseam way off
    assert not pants.match("")


def test_shirt_exact_and_multi_notation():
    assert shirt.match("L").level is Match.EXACT
    assert shirt.match("L / 40 / 12").level is Match.EXACT


def test_shirt_converted():
    assert shirt.match("FR 42").level is Match.EQUIVALENT
    assert shirt.match("41").level is Match.EQUIVALENT
    assert shirt.match("IT 52").level is Match.EQUIVALENT
    assert shirt.match("16").level is Match.EQUIVALENT


def test_shirt_close_and_reject():
    assert shirt.match("M").level is Match.CLOSE
    assert shirt.match("XL").level is Match.CLOSE
    assert not shirt.match("S")
    assert not shirt.match("XXL")
