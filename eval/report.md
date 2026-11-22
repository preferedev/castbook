# Castbook attribution eval
_2026-11-22T07:01:17+00:00Z — llamacpp:Qwen3-4B-Instruct-2507-Q4_K_M_

| book | units | labeled | correct | accuracy | ambiguous |
|---|---|---|---|---|---|
| alice-in-wonderland | 107 | 21 | 20 | 95% | 0 |
| pride-and-prejudice | 29 | 20 | 8 | 40% | 0 |

## Misses

- **alice-in-wonderland** `ch006-u0004` expected `ambiguous` got `march hare` — 'The table was a large one, but the three were all crowded together at one corner'
- **pride-and-prejudice** `ch001-u0003` expected `bennet` got `mr. bennet` — '“I hope Mr. Bingley will like it, Lizzy.”'
- **pride-and-prejudice** `ch001-u0004` expected `bennet` got `mrs. bennet` — '“We are not in a way to know what Mr. Bingley likes,” said her mother resentfull'
- **pride-and-prejudice** `ch001-u0006` expected `bennet` got `mrs. bennet` — '“I do not believe Mrs. Long will do any such thing. She has two nieces of her ow'
- **pride-and-prejudice** `ch001-u0007` expected `bennet` got `mr. bennet` — '“No more have I,” said Mr. Bennet; “and I am glad to find that you do not depend'
- **pride-and-prejudice** `ch001-u0009` expected `bennet` got `mrs. bennet` — '“Don’t keep coughing so, Kitty, for heaven’s sake! Have a little compassion on m'
- **pride-and-prejudice** `ch001-u0010` expected `bennet` got `mr. bennet` — '“Kitty has no discretion in her coughs,” said her father; “she times them ill.”'
- **pride-and-prejudice** `ch001-u0012` expected `kitty` got `narrator` — '“When is your next ball to be, Lizzy?”'
- **pride-and-prejudice** `ch001-u0013` expected `elizabeth` got `kitty` — '“Tomorrow fortnight.”'
- **pride-and-prejudice** `ch001-u0015` expected `bennet` got `elizabeth` — '“Then, my dear, you may have the advantage of your friend, and introduce Mr. Bin'
- **pride-and-prejudice** `ch001-u0016` expected `bennet` got `mrs. bennet` — '“Impossible, Mr. Bennet, impossible, when I am not acquainted with him myself; h'
- **pride-and-prejudice** `ch001-u0018` expected `bennet` got `narrator` — 'The girls stared at their father. Mrs. Bennet said only, “Nonsense, nonsense!”'
- **pride-and-prejudice** `ch001-u0020` expected `narrator` got `mary` — 'Mary wished to say something very sensible, but knew not how.'
