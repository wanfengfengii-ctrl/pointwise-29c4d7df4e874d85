def _better(candidate, best):
    """True when ``candidate`` beats ``best`` under the three-level verdict.

    States are ``(covered count, total samples, segments)``: maximize covered,
    then minimize samples, then take the lexicographically smallest sequence.
    """
    if candidate[0] != best[0]:
        return candidate[0] > best[0]
    if candidate[1] != best[1]:
        return candidate[1] < best[1]
    return candidate[2] < best[2]


def select_segments(candidates, max_segments, max_samples):
    """Choose non-overlapping half-open review segments over candidate indices.

    ``candidates`` is an iterable of distinct global zero-based indices; it is
    sorted and deduplicated internally. Every segment must start and end on a
    candidate (``lo`` and ``hi - 1`` respectively). Segments stay disjoint but
    may be adjacent and may span gaps without candidates.

    The verdict is lexicographic:

    1. maximize the number of unique candidates covered;
    2. among ties, minimize the total number of samples read (sum of ``hi-lo``);
    3. among remaining ties, take the lexicographically smallest sequence of
       ``(lo, hi)`` pairs.

    Returns ``(segments, covered_indices, total_samples)`` where ``segments`` is
    a list of ``[lo, hi]`` lists and ``covered_indices`` is a sorted list.
    """
    points = sorted(set(candidates))
    n = len(points)
    if max_segments <= 0 or max_samples <= 0 or n == 0:
        return [], [], 0

    # Singletons cover every candidate with n segments and n samples; when both
    # budgets allow that, the verdict is trivially all singletons.
    if max_segments >= n and max_samples >= n:
        segments = [[point, point + 1] for point in points]
        return segments, list(points), n

    # No feasible segment can be longer than the full candidate span plus one,
    # even when the raw read budget is larger.
    budget = min(max_samples, points[-1] - points[0] + 1)
    layers = min(max_segments, n, budget)
    empty = (0, [])

    # Knapsack prefix DP.
    #   dp[k][j][s] = (covered, segments) for the best plan over the first j
    #   candidates using at most k segments and exactly s reads; for the same
    #   (k, j, s) only the plan with the most covered candidates, then the
    #   lexicographically smallest sequence, is retained. Coverage is monotone
    #   in read budget, so maximizing covered per cost and finally scanning for
    #   the (largest covered, smallest cost, smallest sequence) yields the
    #   three-level verdict without retaining a Pareto frontier per cell.
    dp = [
        [[None] * (budget + 1) for _ in range(n + 1)]
        for _ in range(layers + 1)
    ]
    for k in range(layers + 1):
        dp[k][0][0] = empty
    for j in range(1, n + 1):
        dp[0][j][0] = empty

    for k in range(1, layers + 1):
        for j in range(1, n + 1):
            row = dp[k][j]
            # Skip candidate j-1: best plan over the first j-1 candidates.
            for cost, state in enumerate(dp[k][j - 1]):
                if state is not None:
                    row[cost] = state
            hi = points[j - 1] + 1
            # Close a segment [points[i-1], hi) over candidates i-1..j-1.
            # A feasible segment never exceeds the read budget, so the start
            # candidate must lie within max_samples samples of hi.
            for i in range(j, 0, -1):
                length = hi - points[i - 1]
                if length > budget:
                    break
                gained = j - i + 1
                head_row = dp[k - 1][i - 1]
                for head_cost in range(budget - length + 1):
                    head_state = head_row[head_cost]
                    if head_state is None:
                        continue
                    head_covered, head_segments = head_state
                    plan = (
                        head_covered + gained,
                        head_segments + [[points[i - 1], hi]],
                    )
                    cost = head_cost + length
                    kept = row[cost]
                    if kept is None or plan[0] > kept[0] or (
                        plan[0] == kept[0] and plan[1] < kept[1]
                    ):
                        row[cost] = plan

    best = None
    for cost, state in enumerate(dp[layers][n]):
        if state is None:
            continue
        plan = (state[0], cost, state[1])
        if best is None or _better(plan, best):
            best = plan
    _, total_samples, segments = best
    covered_indices = covered_candidates(points, segments)
    return [list(segment) for segment in segments], covered_indices, total_samples


def covered_candidates(candidates, segments):
    """Sorted unique candidate indices falling inside any chosen segment."""
    points = sorted(set(candidates))
    return [
        point
        for point in points
        if any(lo <= point < hi for lo, hi in segments)
    ]
