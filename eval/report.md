# Castbook attribution eval
_2026-11-22T07:15:49+00:00Z — llamacpp:Qwen3-4B-Instruct-2507-Q4_K_M_

| book | units | labeled | correct | accuracy | ambiguous |
|---|---|---|---|---|---|
| alice-in-wonderland | 107 | 21 | 20 | 95% | 0 |
| pride-and-prejudice | 29 | 20 | 15 | 75% | 0 |

## Misses

- **alice-in-wonderland** `ch006-u0004` expected `ambiguous` got `march hare` — 'The table was a large one, but the three were all crowded together at one corner'
- **pride-and-prejudice** `ch001-u0012` expected `kitty` got `narrator` — '“When is your next ball to be, Lizzy?”'
- **pride-and-prejudice** `ch001-u0013` expected `elizabeth` got `kitty` — '“Tomorrow fortnight.”'
- **pride-and-prejudice** `ch001-u0015` expected `bennet` got `elizabeth` — '“Then, my dear, you may have the advantage of your friend, and introduce Mr. Bin'
- **pride-and-prejudice** `ch001-u0018` expected `bennet` got `narrator` — 'The girls stared at their father. Mrs. Bennet said only, “Nonsense, nonsense!”'
- **pride-and-prejudice** `ch001-u0020` expected `narrator` got `mary` — 'Mary wished to say something very sensible, but knew not how.'
