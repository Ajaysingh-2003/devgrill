"""Glicko-2 against Glickman's worked example, plus properties any correct implementation has."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from devgrill.domain.glicko2 import SCALE, Rating, Result, expected_score, rate

# "Example of the Glicko-2 system" (Glickman, 2012), section "Example calculation".
PLAYER = Rating(1500, 200, 0.06)
GAMES = [
    Result(Rating(1400, 30), 1.0),
    Result(Rating(1550, 100), 0.0),
    Result(Rating(1700, 300), 0.0),
]


def test_matches_glickmans_worked_example() -> None:
    new = rate(PLAYER, GAMES, tau=0.5)
    # The paper reports the Glicko-2 scale results to 4-5 significant digits.
    assert (new.rating - 1500) / SCALE == pytest.approx(-0.2069, abs=1e-4)
    assert new.rd / SCALE == pytest.approx(0.8722, abs=1e-4)
    assert new.vol == pytest.approx(0.05999, abs=1e-4)
    # ...and on the Glicko scale: r' = 1464.06, RD' = 151.52.
    assert new.rating == pytest.approx(1464.06, abs=0.01)
    assert new.rd == pytest.approx(151.52, abs=0.01)


def test_no_games_only_widens_the_deviation() -> None:
    new = rate(PLAYER, [])
    assert new.rating == PLAYER.rating
    assert new.vol == PLAYER.vol
    assert new.rd == pytest.approx(SCALE * ((200 / SCALE) ** 2 + 0.06**2) ** 0.5)


def test_rejects_scores_outside_unit_interval() -> None:
    with pytest.raises(ValueError):
        Result(Rating(), 1.5)


def test_rejects_non_positive_deviation() -> None:
    with pytest.raises(ValueError):
        Rating(1500, 0)


ratings = st.builds(
    Rating,
    rating=st.floats(min_value=600, max_value=2600),
    rd=st.floats(min_value=30, max_value=350),
    vol=st.floats(min_value=0.03, max_value=0.12),
)
scores = st.floats(min_value=0, max_value=1)


@given(player=ratings, opponent=ratings)
def test_expected_scores_are_complementary_for_equal_uncertainty(
    player: Rating, opponent: Rating
) -> None:
    a = Rating(player.rating, 100, player.vol)
    b = Rating(opponent.rating, 100, opponent.vol)
    assert expected_score(a, b) + expected_score(b, a) == pytest.approx(1.0)


@given(player=ratings, opponent=ratings)
def test_winning_never_rates_lower_than_losing(player: Rating, opponent: Rating) -> None:
    win = rate(player, [Result(opponent, 1.0)])
    loss = rate(player, [Result(opponent, 0.0)])
    assert win.rating >= loss.rating


@given(player=ratings, opponent=ratings, score=scores)
def test_playing_makes_the_rating_more_certain(
    player: Rating, opponent: Rating, score: float
) -> None:
    # A game always shrinks RD below the pre-game deviation (step 6, phi*). Note phi* uses
    # the *new* volatility: a shock result can raise volatility, so comparing against an
    # inactive period with the old volatility would be wrong.
    new = rate(player, [Result(opponent, score)])
    phi_star = ((player.rd / SCALE) ** 2 + new.vol**2) ** 0.5 * SCALE
    assert new.rd <= phi_star + 1e-9


@given(player=ratings, opponent=ratings)
def test_beating_expectation_raises_the_rating(player: Rating, opponent: Rating) -> None:
    e = expected_score(player, opponent)
    new = rate(player, [Result(opponent, min(1.0, e + 0.2))])
    assert new.rating >= player.rating - 1e-9


@given(player=ratings, opponent=ratings, score=scores)
def test_outputs_stay_finite_and_positive(player: Rating, opponent: Rating, score: float) -> None:
    new = rate(player, [Result(opponent, score)])
    assert new.rd > 0
    assert new.vol > 0
    assert 0 < new.rating < 5000
