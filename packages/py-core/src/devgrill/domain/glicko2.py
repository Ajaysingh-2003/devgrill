"""Glicko-2 ratings (Mark Glickman, "Example of the Glicko-2 system", 2012 revision).

DevGrill rates players and scenarios against each other: a resolved incident is a game the
player played against the scenario. Scores are in [0, 1], so partial credit (for example a
fix that passes most verify probes) is a draw-like result rather than a plain win or loss.

The step numbers in the comments follow the paper so the code can be checked against it.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

#: Converts between the Glicko scale (1500 ± 350) and the Glicko-2 scale (0 ± 2.01).
SCALE: Final = 173.7178
#: Constrains how fast volatility changes. Glickman suggests 0.3 to 1.2; 0.5 is the paper's example.
DEFAULT_TAU: Final = 0.5
#: Convergence tolerance for the volatility iteration (step 5).
EPSILON: Final = 1e-6

DEFAULT_RATING: Final = 1500.0
DEFAULT_RD: Final = 350.0
DEFAULT_VOLATILITY: Final = 0.06


@dataclass(frozen=True, slots=True)
class Rating:
    """A Glicko-2 rating on the familiar Glicko scale."""

    rating: float = DEFAULT_RATING
    rd: float = DEFAULT_RD
    vol: float = DEFAULT_VOLATILITY

    def __post_init__(self) -> None:
        if self.rd <= 0:
            raise ValueError("rating deviation must be positive")
        if self.vol <= 0:
            raise ValueError("volatility must be positive")


@dataclass(frozen=True, slots=True)
class Result:
    """One game in a rating period: the opponent's rating and this player's score in [0, 1]."""

    opponent: Rating
    score: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.score <= 1.0:
            raise ValueError("score must be between 0 and 1")


def _g(phi: float) -> float:
    return 1.0 / math.sqrt(1.0 + 3.0 * phi * phi / (math.pi * math.pi))


def _expected(mu: float, mu_j: float, phi_j: float) -> float:
    return 1.0 / (1.0 + math.exp(-_g(phi_j) * (mu - mu_j)))


def expected_score(player: Rating, opponent: Rating) -> float:
    """Probability-like expected score of `player` against `opponent`."""
    return _expected(
        (player.rating - DEFAULT_RATING) / SCALE,
        (opponent.rating - DEFAULT_RATING) / SCALE,
        opponent.rd / SCALE,
    )


def _new_volatility(phi: float, sigma: float, delta: float, v: float, tau: float) -> float:
    """Step 5: solve for the new volatility with the Illinois variant of regula falsi."""
    a = math.log(sigma * sigma)

    def f(x: float) -> float:
        ex = math.exp(x)
        num = ex * (delta * delta - phi * phi - v - ex)
        den = 2.0 * (phi * phi + v + ex) ** 2
        return num / den - (x - a) / (tau * tau)

    big_a = a
    if delta * delta > phi * phi + v:
        big_b = math.log(delta * delta - phi * phi - v)
    else:
        k = 1
        while f(a - k * tau) < 0:
            k += 1
        big_b = a - k * tau

    f_a, f_b = f(big_a), f(big_b)
    while abs(big_b - big_a) > EPSILON:
        big_c = big_a + (big_a - big_b) * f_a / (f_b - f_a)
        f_c = f(big_c)
        if f_c * f_b <= 0:
            big_a, f_a = big_b, f_b
        else:
            f_a /= 2.0
        big_b, f_b = big_c, f_c
    return math.exp(big_a / 2.0)


def rate(player: Rating, results: Iterable[Result], tau: float = DEFAULT_TAU) -> Rating:
    """Return the player's rating after one rating period containing `results`.

    With no results, only the rating deviation grows (step 6 alone): an inactive player's
    rating becomes less certain over time.
    """
    games = list(results)

    # Step 2: convert to the Glicko-2 scale.
    mu = (player.rating - DEFAULT_RATING) / SCALE
    phi = player.rd / SCALE
    sigma = player.vol

    if not games:
        phi_star = math.sqrt(phi * phi + sigma * sigma)
        return Rating(player.rating, phi_star * SCALE, sigma)

    # Steps 3 and 4: estimated variance v and improvement delta.
    v_inv = 0.0
    total = 0.0
    for game in games:
        mu_j = (game.opponent.rating - DEFAULT_RATING) / SCALE
        phi_j = game.opponent.rd / SCALE
        g_j = _g(phi_j)
        e_j = _expected(mu, mu_j, phi_j)
        v_inv += g_j * g_j * e_j * (1.0 - e_j)
        total += g_j * (game.score - e_j)
    v = 1.0 / v_inv
    delta = v * total

    # Step 5: new volatility.
    sigma_new = _new_volatility(phi, sigma, delta, v, tau)

    # Steps 6 and 7: new deviation and rating.
    phi_star = math.sqrt(phi * phi + sigma_new * sigma_new)
    phi_new = 1.0 / math.sqrt(1.0 / (phi_star * phi_star) + 1.0 / v)
    mu_new = mu + phi_new * phi_new * total

    # Step 8: back to the Glicko scale.
    return Rating(mu_new * SCALE + DEFAULT_RATING, phi_new * SCALE, sigma_new)
