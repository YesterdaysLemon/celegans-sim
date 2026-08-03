"""The mechanics must be right independently of the biology sitting on top of them."""

import numpy as np
import pytest

from worm.body import Body, radius_profile
from worm.params import MEDIA, Params


@pytest.fixture(scope="module")
def params():
    return Params()


def test_heading_argument_points_the_body_backwards(params):
    """`heading` is where the body trails; the animal faces `heading + pi`.

    Pinned because nothing pinned it and two callers got it wrong. `position` is node 0,
    which `nodes()` documents as the nose, and the body is laid out along `+heading` from
    there -- so the constructor argument named for where the animal points sets the
    direction it points *away* from. Everything that actually asks for a direction uses
    `body_direction`, which is right, so the convention was exercised constantly and
    asserted nowhere; the only two places it ever surfaced were a caller translating "aim
    at X" into a heading, and both aimed at the reflection of X.

    Geometry alone settles it, so this costs nothing: `body_direction` is the travel axis
    by `engine.py`'s own definition of forward, and it is antiparallel to `heading`.
    """
    for heading in (0.0, 0.7, np.pi / 2, 2.5, np.pi, -1.2):
        b = Body(params.body, MEDIA["agar"], position=(3.0, -1.0), heading=heading)

        # The nose is at `position`, not the centroid and not the tail.
        assert np.allclose(b.nodes()[0], (3.0, -1.0))

        # ...and the rest of the body lies on the far side of it from where it will go.
        forward = np.arctan2(*b.body_direction()[::-1])
        wrapped = (forward - (heading + np.pi) + np.pi) % (2.0 * np.pi) - np.pi
        assert abs(wrapped) < 1e-12, (
            "body_direction is %.6f rad for heading %.6f; expected heading + pi"
            % (forward, heading))

    # The accessor named `heading` returns the argument, not the facing. If this ever
    # starts returning the travel axis instead, the docstring on it is the thing to fix
    # first -- it has said both at different times.
    b = Body(params.body, MEDIA["agar"], heading=0.9)
    assert b.heading() == pytest.approx(0.9)


def test_body_is_inextensible(params):
    """Length is exact by construction, not enforced by stiff springs."""
    b = Body(params.body, MEDIA["agar"])
    rng = np.random.default_rng(0)
    for _ in range(200):
        b.step(rng.normal(0, 0.4, b.n - 1))
    seg = np.linalg.norm(np.diff(b.nodes(), axis=0), axis=1)
    assert np.allclose(seg, params.body.length / b.n, rtol=1e-12)


def test_drag_matrix_matches_direct_quadrature(params):
    """The assembled drag metric must equal the integral it stands for."""
    b = Body(params.body, MEDIA["agar"])
    rng = np.random.default_rng(1)
    b.theta = np.cumsum(rng.normal(0, 0.08, b.n))
    u = np.stack([np.cos(b.theta), np.sin(b.theta)], axis=1)
    nv = np.stack([-u[:, 1], u[:, 0]], axis=1)
    D = b._drag_matrix(u, nv)

    gx, gw = np.polynomial.legendre.leggauss(4)
    s_pts, w_pts = 0.5 * (gx + 1), 0.5 * gw
    n, l = b.n, b.l
    C_T, C_N = MEDIA["agar"].c_tangential, MEDIA["agar"].c_normal
    ref = np.zeros((n + 2, n + 2))
    for k in range(n):
        lam = b.rho[k] * (C_T * np.outer(u[k], u[k]) + C_N * np.outer(nv[k], nv[k]))
        for s, wq in zip(s_pts, w_pts):
            J = np.zeros((2, n + 2))
            J[0, 0] = J[1, 1] = 1.0
            for m in range(n):
                w = 1.0 if m < k else (s if m == k else 0.0)
                J[:, 2 + m] = l * w * nv[m]
            ref += l * wq * (J.T @ lam @ J)
    assert np.abs(D - ref).max() / np.abs(ref).max() < 1e-12


def test_drag_matrix_is_positive_definite(params):
    b = Body(params.body, MEDIA["agar"])
    rng = np.random.default_rng(2)
    b.theta = np.cumsum(rng.normal(0, 0.1, b.n))
    u = np.stack([np.cos(b.theta), np.sin(b.theta)], axis=1)
    nv = np.stack([-u[:, 1], u[:, 0]], axis=1)
    D = b._drag_matrix(u, nv)
    assert np.linalg.eigvalsh(0.5 * (D + D.T)).min() > 0


def test_passive_body_relaxes_straight(params):
    """An unpowered bent worm straightens, and its bending energy never increases."""
    b = Body(params.body, MEDIA["agar"])
    b.theta = 0.6 * np.sin(np.linspace(0, 3 * np.pi, b.n))
    zero = np.zeros(b.n - 1)
    energy = []
    for i in range(4000):
        b.step(zero)
        if i % 100 == 0:
            j = np.diff(b.theta)
            energy.append(float((b.K * j * j).sum()))
    energy = np.array(energy)
    assert np.all(np.diff(energy) <= 1e-12)
    assert energy[-1] < 1e-3 * energy[0]
    assert np.abs(b.curvature()).max() < 0.2


@pytest.mark.parametrize("medium", ["buffer", "viscous", "agar"])
def test_swimming_speed_matches_resistive_force_theory(params, medium):
    """Gray-Hancock: an undulating body's progress is set by the drag anisotropy.

    U/c = (K-1)B / (1 + KB) for a small-amplitude travelling wave. Agreement to a few
    percent is the most that can be expected -- the theory is a small-amplitude limit and
    the body here is finite and discrete -- but the number must track K over its whole
    25-fold range, because that anisotropy is the only thing separating a swim from a crawl.
    """
    med = MEDIA[medium]
    b = Body(params.body, med)
    b.rho[:] = 1.0                       # uniform drag, matching the theory's assumptions
    b._precompute_masks()
    L, lam, amp, f = 1.0, 0.65, 0.015, 0.5
    kw, c = 2 * np.pi / lam, f * 0.65
    s = (np.arange(b.n) + 0.5) / b.n * L
    steps, T = 6000, 1.0 / f
    dt = T / steps
    x = np.zeros(2)
    for i in range(steps):
        t = i * dt
        th = amp * kw * np.cos(kw * (s - c * t))
        thd = amp * kw * kw * c * np.sin(kw * (s - c * t))
        u = np.stack([np.cos(th), np.sin(th)], axis=1)
        nv = np.stack([-u[:, 1], u[:, 0]], axis=1)
        b.theta = th
        D = b._drag_matrix(u, nv)
        x = x - np.linalg.solve(D[:2, :2], D[:2, 2:] @ thd) * dt

    K = med.anisotropy
    B = 2 * np.pi ** 2 * amp ** 2 / lam ** 2
    predicted = (K - 1) * B / (1 + K * B)
    measured = -x[0] / T / c
    assert abs(measured - predicted) / predicted < 0.06


def test_radius_profile_shape():
    s = np.linspace(0, 1, 200)
    r = radius_profile(s, 0.035)
    assert r.max() <= 0.035 + 1e-12
    assert 0.35 < s[np.argmax(r)] < 0.65        # widest near the middle
    assert r[0] < 0.6 * r.max() and r[-1] < 0.6 * r.max()   # tapered at both ends
    assert r[-1] < r[0]                          # tail thinner than head


def test_self_contact_is_inert_on_a_straight_body(params):
    """A straight worm is a continuous tube, not a pile of collisions.

    Adjacent nodes are 0.021 mm apart against a midbody contact distance near 0.07, so a
    naive all-pairs check reports overlap everywhere along a perfectly straight animal.
    The eligibility rule -- a pair counts only once its separation along the body exceeds
    its own width -- is what makes the force mean anything, and this is that rule.
    """
    body = Body(params.body, params.medium)
    f = body.self_contact_force(body.nodes())
    assert np.abs(f).max() == 0.0


def test_self_contact_pushes_a_folded_body_apart(params):
    """The force has to fire when the body actually folds through itself.

    Built by hand rather than by driving the model there, because the model does not go
    there: tools/self_contact.py measures no overlap at any scale. A constraint that has
    never been observed to act needs a test that makes it act, or it is only assumed to
    work.
    """
    body = Body(params.body, params.medium)
    n = body.n
    # A hairpin: the front half doubles back over the rear half, one contact distance
    # apart would be touching, so half of that is frank interpenetration.
    body.theta = np.zeros(n)
    body.theta[n // 2:] = np.pi
    nodes = body.nodes()
    nodes[n // 2 + 1:, 1] += 0.5 * (2 * params.body.radius_max)

    f = body.self_contact_force(nodes)
    assert np.abs(f).max() > 0.0, "a folded body must register self-contact"

    # Equal and opposite: this is an internal force and must not accelerate the animal.
    assert np.allclose(f.sum(axis=0), 0.0, atol=1e-9)

    # And it must separate the two limbs rather than pull them together. The overlapping
    # front half is displaced +y, so it must be pushed further +y.
    front = f[n // 2 + 1:, 1].sum()
    rear = f[: n // 2, 1].sum()
    assert front > 0.0 and rear < 0.0


def test_self_contact_ignores_pairs_that_only_just_qualify(params):
    """The eligibility margin is the whole reason this force is safe to switch on.

    Nodes 31 and 34 are 0.0625 mm apart along the body against a combined width of
    0.06224 -- a margin of three ten-thousandths of a millimetre. Requiring only that
    separation exceed width admits that pair, ordinary undulation closes it, and the force
    fires on a normally-crawling animal. It moved one 3 mm off its own trajectory.
    """
    body = Body(params.body, params.medium)
    along = np.abs(np.arange(body.n + 1)[:, None]
                   - np.arange(body.n + 1)[None, :]) * body.l
    naive = np.triu(along > body._self_contact_dist, k=1)
    assert naive[31, 34], "the pair that caused the bug must qualify under the naive rule"
    assert not body._self_pairs[31, 34], "and must not qualify under the real one"
    # A genuine fold is far past the cut and must be unaffected by the margin.
    assert body._self_pairs[5, body.n - 5]
