# Castbook attribution eval
_2026-11-22T17:01:57+00:00Z — heuristic_

| book | units | labeled | correct | accuracy | ambiguous |
|---|---|---|---|---|---|
| alice-in-wonderland | 146 | 21 | 18 | 86% | 0 |
| dorian-gray | 21 | 16 | 13 | 81% | 0 |
| dr-jekyll-and-mr-hyde | 28 | 20 | 19 | 95% | 0 |
| great-expectations | 46 | 34 | 32 | 94% | 2 |
| huckleberry-finn | 27 | 20 | 17 | 85% | 1 |
| jane-eyre | 26 | 20 | 18 | 90% | 0 |
| moby-dick | 36 | 20 | 16 | 80% | 2 |
| pride-and-prejudice | 34 | 20 | 15 | 75% | 1 |
| sherlock-holmes | 36 | 29 | 26 | 90% | 0 |
| treasure-island | 35 | 25 | 22 | 88% | 0 |

## Misses

- **alice-in-wonderland** `ch006-u0005` expected `ambiguous` got `alice` — 'The table was a large one, but the three were all crowded together at one corner'
- **alice-in-wonderland** `ch006-u0017` expected `hatter` got `alice` — 'The Hatter opened his eyes very wide on hearing this; but all he said was, “Why '
- **alice-in-wonderland** `ch006-u0031` expected `alice` got `dormouse` — 'Alice considered a little, and then said “The fourth.”'
- **dorian-gray** `ch000-u0003` expected `basil-hallward` got `lord-henry-wotton` — '“That entirely depends on how you sit to-day, Dorian.”'
- **dorian-gray** `ch000-u0006` expected `basil-hallward` got `lord-henry-wotton` — '“This is Lord Henry Wotton, Dorian, an old Oxford friend of mine. I\nhave just be'
- **dorian-gray** `ch000-u0011` expected `lord-henry-wotton` got `dorian-gray` — '“Oh, I will make your peace with my aunt. She is quite devoted to you.\nAnd I don'
- **dr-jekyll-and-mr-hyde** `ch001-u0027` expected `mr.-enfield` got `mr-utterson` — 'Mr. Utterson sighed deeply but said never a word; and the young man\npresently re'
- **great-expectations** `ch001-u0005` expected `magwitch` got `ambiguous` — '“Hold your noise!” cried a terrible voice, as a man started up from\namong the gr'
- **great-expectations** `ch001-u0037` expected `pip` got `abel-magwitch` — '“My sister, sir,—Mrs. Joe Gargery,—wife of Joe Gargery, the blacksmith,\nsir.”'
- **huckleberry-finn** `ch008-u0003` expected `jim` got `ambiguous` — '“Doan’ hurt me—don’t! I hain’t ever done no harm to a ghos’. I alwuz\nliked dead '
- **huckleberry-finn** `ch008-u0006` expected `jim` got `huckleberry-finn` — '“What’s de use er makin’ up de camp fire to cook strawbries en sich\ntruck? But y'
- **huckleberry-finn** `ch008-u0019` expected `jim` got `huckleberry-finn` — '“No! W’y, what has you lived on? But you got a gun. Oh, yes, you got a\ngun. Dat’'
- **jane-eyre** `ch023-u0020` expected `jane-eyre` got `rochester` — '“I am no bird; and no net ensnares me; I am a free human being with an\nindepende'
- **jane-eyre** `ch023-u0024` expected `jane-eyre` got `rochester` — '“You play a farce, which I merely laugh at.”'
- **moby-dick** `ch036-u0012` expected `crew` got `ahab` — '“Sing out for him!” was the impulsive rejoinder from a score of clubbed\nvoices.'
- **moby-dick** `ch036-u0015` expected `crew` got `ahab` — '“Lower away, and after him!”'
- **moby-dick** `ch036-u0017` expected `crew` got `ahab` — '“A dead whale or a stove boat!”'
- **moby-dick** `ch036-u0020` expected `ahab` got `ambiguous` — '“All ye mast-headers have before now heard me give orders about a white\nwhale. L'
- **pride-and-prejudice** `ch001-u0006` expected `bennet` got `elizabeth` — '“I do not believe Mrs. Long will do any such thing. She has two nieces of her ow'
- **pride-and-prejudice** `ch001-u0014` expected `kitty` got `bennet` — '“When is your next ball to be, Lizzy?”'
- **pride-and-prejudice** `ch001-u0015` expected `elizabeth` got `kitty` — '“Tomorrow fortnight.”'
- **pride-and-prejudice** `ch001-u0018` expected `bennet` got `kitty` — '“Impossible, Mr. Bennet, impossible, when I am not acquainted with him myself; h'
- **pride-and-prejudice** `ch001-u0019` expected `bennet` got `kitty` — '“I honour your circumspection. A fortnight’s acquaintance is certainly very litt'
- **sherlock-holmes** `ch001-u0026` expected `holmes` got `john-watson` — '“Quite so! You have not observed. And yet you have seen. That is just\nmy point. '
- **sherlock-holmes** `ch001-u0030` expected `watson` got `sherlock-holmes` — '“There will call upon you to-night, at a quarter to eight o’clock,” it\nsaid, “a '
- **sherlock-holmes** `ch001-u0033` expected `holmes` got `john-watson` — '“I have no data yet. It is a capital mistake to theorise before one has\ndata. In'
- **treasure-island** `ch001-u0002` expected `long-john-silver` got `jim-hawkins` — '“Yes, my lad,” said he;'
- **treasure-island** `ch001-u0004` expected `long-john-silver` got `jim-hawkins` — '“Oh!” said he, quite loud, and offering his hand.'
- **treasure-island** `ch001-u0029` expected `long-john-silver` got `jim-hawkins` — '“Keel-hauling, was you? And a mighty suitable thing, too, and you may\nlay to tha'
