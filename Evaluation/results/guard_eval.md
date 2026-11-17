# Safety layers: evaluation

- Attacks tested: 57; refused by the guard: **57/57** (100.0%)
- Benign queries tested: 32; allowed by the guard: **32/32** (100.0%); executed successfully: 32/32

## Attacks by category

| Category | Attacks | Guard refuses | Engine alone refuses |
| --- | --- | --- | --- |
| write | 13 | 13/13 | 10/13 |
| cte-write | 3 | 3/3 | 3/3 |
| stacked | 4 | 4/4 | 3/4 |
| obfuscated | 4 | 4/4 | 4/4 |
| file-read | 10 | 10/10 | 10/10 |
| file-write | 3 | 3/3 | 3/3 |
| engine | 20 | 20/20 | 10/20 |

## Attacks the guard let through

None.

## Benign queries wrongly refused or failing

None.

## Defence in depth

43/57 attacks would also fail on the locked engine alone. 14 are stopped ONLY by the guard (mostly writes on the in-memory copy, which the engine permits); the guard is therefore necessary, and the engine lock covers file and configuration access independently.