# Castbook attribution eval
_2026-11-22T14:55:03+00:00Z — llamacpp:Qwen3-4B-Instruct-2507-Q4_K_M_

| book | units | labeled | correct | accuracy | ambiguous |
|---|---|---|---|---|---|
| alice-in-wonderland | 107 | 21 | 20 | 95% | 0 |
| pride-and-prejudice | 29 | 20 | 17 | 85% | 0 |

## Misses

- **alice-in-wonderland** `ch006-u0004` expected `ambiguous` got `march hare` — 'The table was a large one, but the three were all crowded together at one corner'
- **pride-and-prejudice** `ch001-u0012` expected `kitty` got `elizabeth` — '“When is your next ball to be, Lizzy?”'
- **pride-and-prejudice** `ch001-u0015` expected `bennet` got `elizabeth` — '“Then, my dear, you may have the advantage of your friend, and introduce Mr. Bin'
- **pride-and-prejudice** `ch001-u0017` expected `bennet` got `elizabeth` — '“I honour your circumspection. A fortnight’s acquaintance is certainly very litt'
