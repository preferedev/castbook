# Castbook attribution eval
_2026-11-22T07:02:51+00:00Z — heuristic_

| book | units | labeled | correct | accuracy | ambiguous |
|---|---|---|---|---|---|
| alice-in-wonderland | 107 | 21 | 17 | 81% | 2 |
| pride-and-prejudice | 29 | 20 | 10 | 50% | 8 |

## Misses

- **alice-in-wonderland** `ch006-u0004` expected `ambiguous` got `alice` — 'The table was a large one, but the three were all crowded together at one corner'
- **alice-in-wonderland** `ch006-u0006` expected `alice` got `march-hare` — 'Alice looked all round the table, but there was nothing on it but tea. “I don’t '
- **alice-in-wonderland** `ch006-u0013` expected `hatter` got `alice` — 'The Hatter opened his eyes very wide on hearing this; but all he said was, “Why '
- **alice-in-wonderland** `ch006-u0024` expected `alice` got `hatter` — 'Alice considered a little, and then said “The fourth.”'
- **pride-and-prejudice** `ch001-u0003` expected `bennet` got `ambiguous` — '“I hope Mr. Bingley will like it, Lizzy.”'
- **pride-and-prejudice** `ch001-u0004` expected `bennet` got `ambiguous` — '“We are not in a way to know what Mr. Bingley likes,” said her mother resentfull'
- **pride-and-prejudice** `ch001-u0006` expected `bennet` got `elizabeth` — '“I do not believe Mrs. Long will do any such thing. She has two nieces of her ow'
- **pride-and-prejudice** `ch001-u0009` expected `bennet` got `ambiguous` — '“Don’t keep coughing so, Kitty, for heaven’s sake! Have a little compassion on m'
- **pride-and-prejudice** `ch001-u0010` expected `bennet` got `ambiguous` — '“Kitty has no discretion in her coughs,” said her father; “she times them ill.”'
- **pride-and-prejudice** `ch001-u0013` expected `elizabeth` got `kitty` — '“Tomorrow fortnight.”'
- **pride-and-prejudice** `ch001-u0014` expected `bennet` got `kitty` — '“Aye, so it is,” cried her mother, “and Mrs. Long does not come back till the da'
- **pride-and-prejudice** `ch001-u0015` expected `bennet` got `kitty` — '“Then, my dear, you may have the advantage of your friend, and introduce Mr. Bin'
- **pride-and-prejudice** `ch001-u0016` expected `bennet` got `kitty` — '“Impossible, Mr. Bennet, impossible, when I am not acquainted with him myself; h'
- **pride-and-prejudice** `ch001-u0017` expected `bennet` got `kitty` — '“I honour your circumspection. A fortnight’s acquaintance is certainly very litt'
