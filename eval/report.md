# Castbook attribution eval
_2026-11-22T16:50:19+00:00Z — heuristic_

| book | units | labeled | correct | accuracy | ambiguous |
|---|---|---|---|---|---|
| alice-in-wonderland | 107 | 21 | 19 | 90% | 0 |
| dorian-gray | 17 | 16 | 14 | 88% | 0 |
| dr-jekyll-and-mr-hyde | 20 | 20 | 19 | 95% | 0 |
| great-expectations | 35 | 35 | 33 | 94% | 2 |
| huckleberry-finn | 26 | 20 | 16 | 80% | 4 |
| jane-eyre | 21 | 20 | 20 | 100% | 0 |
| moby-dick | 29 | 20 | 16 | 80% | 1 |
| pride-and-prejudice | 29 | 20 | 14 | 70% | 4 |
| sherlock-holmes | 29 | 29 | 28 | 97% | 0 |
| treasure-island | 25 | 25 | 23 | 92% | 0 |

## Misses

- **alice-in-wonderland** `ch006-u0004` expected `ambiguous` got `alice` — 'The table was a large one, but the three were all crowded together at one corner'
- **alice-in-wonderland** `ch006-u0023` expected `hatter` got `dormouse` — 'The Hatter was the first to break the silence. “What day of the month is it?” he'
- **dorian-gray** `ch000-u0002` expected `basil-hallward` got `lord-henry-wotton` — '“That entirely depends on how you sit to-day, Dorian.”'
- **dorian-gray** `ch000-u0004` expected `basil-hallward` got `lord-henry-wotton` — '“This is Lord Henry Wotton, Dorian, an old Oxford friend of mine. I\nhave just be'
- **dr-jekyll-and-mr-hyde** `ch001-u0020` expected `mr.-enfield` got `mr-utterson` — 'Mr. Utterson sighed deeply but said never a word; and the young man\npresently re'
- **great-expectations** `ch001-u0005` expected `magwitch` got `ambiguous` — '“Hold your noise!” cried a terrible voice, as a man started up from\namong the gr'
- **great-expectations** `ch001-u0035` expected `magwitch` got `ambiguous` — '“You get me a file.” He tilted me again. “And you get me wittles.” He'
- **huckleberry-finn** `ch008-u0001` expected `huckleberry-finn` got `ambiguous` — '“Hello, Jim!” and skipped out.'
- **huckleberry-finn** `ch008-u0003` expected `jim` got `ambiguous` — '“Doan’ hurt me—don’t! I hain’t ever done no harm to a ghos’. I alwuz\nliked dead '
- **huckleberry-finn** `ch008-u0025` expected `jim` got `ambiguous` — '“Maybe I better not tell.”'
- **huckleberry-finn** `ch008-u0026` expected `huckleberry-finn` got `ambiguous` — '“Why, Jim?”'
- **moby-dick** `ch036-u0010` expected `crew` got `ahab` — '“Sing out for him!” was the impulsive rejoinder from a score of clubbed\nvoices.'
- **moby-dick** `ch036-u0013` expected `crew` got `ahab` — '“Lower away, and after him!”'
- **moby-dick** `ch036-u0015` expected `crew` got `ahab` — '“A dead whale or a stove boat!”'
- **moby-dick** `ch036-u0018` expected `ahab` got `ambiguous` — '“All ye mast-headers have before now heard me give orders about a white\nwhale. L'
- **pride-and-prejudice** `ch001-u0010` expected `bennet` got `kitty` — '“Kitty has no discretion in her coughs,” said her father; “she times them ill.”'
- **pride-and-prejudice** `ch001-u0012` expected `kitty` got `bennet` — '“When is your next ball to be, Lizzy?”'
- **pride-and-prejudice** `ch001-u0013` expected `elizabeth` got `kitty` — '“Tomorrow fortnight.”'
- **pride-and-prejudice** `ch001-u0015` expected `bennet` got `kitty` — '“Then, my dear, you may have the advantage of your friend, and introduce Mr. Bin'
- **pride-and-prejudice** `ch001-u0016` expected `bennet` got `kitty` — '“Impossible, Mr. Bennet, impossible, when I am not acquainted with him myself; h'
- **pride-and-prejudice** `ch001-u0019` expected `bennet` got `kitty` — '“What can be the meaning of that emphatic exclamation?” cried he. “Do you consid'
- **sherlock-holmes** `ch001-u0025` expected `watson` got `sherlock-holmes` — '“There will call upon you to-night, at a quarter to eight o’clock,” it\nsaid, “a '
- **treasure-island** `ch001-u0002` expected `long-john-silver` got `jim-hawkins` — '“Yes, my lad,” said he; “such is my name, to be sure. And who may you\nbe?” And t'
- **treasure-island** `ch001-u0003` expected `long-john-silver` got `jim-hawkins` — '“Oh!” said he, quite loud, and offering his hand. “I see. You are our\nnew cabin-'
