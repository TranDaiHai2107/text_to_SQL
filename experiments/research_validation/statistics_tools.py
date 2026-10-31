"""Paired cluster inference; repeated API generations are not extra questions."""
import random
import statistics

UTILITY = {'correct': 1, 'wrong': -10, 'abstained_answerable': 0}


def holm(p_values):
    ordered = sorted(p_values, key=p_values.get)
    previous = 0.0
    adjusted = {}
    for rank, key in enumerate(ordered):
        previous = max(previous, min(1.0, p_values[key] * (len(ordered) - rank)))
        adjusted[key] = previous
    return adjusted


def percentile(sorted_values, q):
    index = (len(sorted_values) - 1) * q
    low = int(index)
    high = min(low + 1, len(sorted_values) - 1)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (index - low)


def paired_clusters(left_replicates, right_replicates, clusters, *, samples=10000, seed=20261029):
    if not left_replicates or len(left_replicates) != len(right_replicates):
        raise ValueError('Aligned nonempty replicate sets required')
    ids = set(clusters)
    if not ids or any(set(r) != ids for r in left_replicates + right_replicates):
        raise ValueError('Every replicate must cover exactly the same questions and clusters')
    grouped = {}
    for key in sorted(ids):
        delta = statistics.mean(UTILITY[a[key]] - UTILITY[b[key]]
                                for a, b in zip(left_replicates, right_replicates))
        grouped.setdefault(clusters[key], []).append(delta)
    sums = [sum(v) for _, v in sorted(grouped.items())]
    sizes = [len(v) for _, v in sorted(grouped.items())]
    observed = sum(sums) / len(ids)
    rng = random.Random(seed)
    boot = []
    extreme = 0
    for _ in range(samples):
        selected = [rng.randrange(len(sums)) for _ in sums]
        boot.append(100 * sum(sums[i] for i in selected) / sum(sizes[i] for i in selected))
        permuted = sum(s * rng.choice((-1, 1)) for s in sums) / len(ids)
        extreme += abs(permuted) >= abs(observed) - 1e-12
    boot.sort()
    return {'delta_RS10': 100 * observed, 'CI95': [percentile(boot, .025), percentile(boot, .975)],
            'p_two_sided': (extreme + 1) / (samples + 1), 'questions': len(ids),
            'clusters': len(sums), 'replicates': len(left_replicates), 'resamples': samples, 'seed': seed}
