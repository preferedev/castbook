# Castbook attribution eval
_2026-11-22T16:25:13+00:00Z — heuristic_

| book | units | labeled | correct | accuracy | ambiguous |
|---|---|---|---|---|---|
| alice-in-wonderland | 107 | 21 | 18 | 86% | 1 |
| dr-jekyll-and-mr-hyde | 20 | 20 | 19 | 95% | 0 |
| great-expectations | 35 | 35 | 25 | 71% | 7 |
| pride-and-prejudice | 29 | 20 | 13 | 65% | 6 |
| sherlock-holmes | 29 | 29 | 19 | 66% | 3 |
| treasure-island | 25 | 25 | 23 | 92% | 0 |

## Misses

- **alice-in-wonderland** `ch006-u0004` expected `ambiguous` got `alice` — 'The table was a large one, but the three were all crowded together at one corner'
- **alice-in-wonderland** `ch006-u0023` expected `hatter` got `dormouse` — 'The Hatter was the first to break the silence. “What day of the month is it?” he'
- **alice-in-wonderland** `ch006-u0024` expected `alice` got `hatter` — 'Alice considered a little, and then said “The fourth.”'
- **dr-jekyll-and-mr-hyde** `ch001-u0020` expected `mr.-enfield` got `mr-utterson` — 'Mr. Utterson sighed deeply but said never a word; and the young man\npresently re'
- **great-expectations** `ch001-u0005` expected `magwitch` got `narrator` — '“Hold your noise!” cried a terrible voice, as a man started up from\namong the gr'
- **great-expectations** `ch001-u0023` expected `pip` got `ambiguous` — '“There, sir!” I timidly explained. “Also Georgiana. That’s my mother.”'
- **great-expectations** `ch001-u0024` expected `magwitch` got `ambiguous` — '“Oh!” said he, coming back. “And is that your father alonger your\nmother?”'
- **great-expectations** `ch001-u0026` expected `magwitch` got `pip` — '“Ha!” he muttered then, considering. “Who d’ye live with,—supposin’\nyou’re kindl'
- **great-expectations** `ch001-u0028` expected `magwitch` got `pip` — '“Blacksmith, eh?” said he. And looked down at his leg.'
- **great-expectations** `ch001-u0030` expected `magwitch` got `ambiguous` — '“Now lookee here,” he said, “the question being whether you’re to be\nlet to live'
- **great-expectations** `ch001-u0031` expected `pip` got `ambiguous` — '“Yes, sir.”'
- **great-expectations** `ch001-u0032` expected `magwitch` got `ambiguous` — '“And you know what wittles is?”'
- **great-expectations** `ch001-u0033` expected `pip` got `ambiguous` — '“Yes, sir.”'
- **great-expectations** `ch001-u0035` expected `magwitch` got `ambiguous` — '“You get me a file.” He tilted me again. “And you get me wittles.” He'
- **pride-and-prejudice** `ch001-u0003` expected `bennet` got `ambiguous` — '“I hope Mr. Bingley will like it, Lizzy.”'
- **pride-and-prejudice** `ch001-u0009` expected `bennet` got `narrator` — '“Don’t keep coughing so, Kitty, for heaven’s sake! Have a little compassion on m'
- **pride-and-prejudice** `ch001-u0010` expected `bennet` got `ambiguous` — '“Kitty has no discretion in her coughs,” said her father; “she times them ill.”'
- **pride-and-prejudice** `ch001-u0013` expected `elizabeth` got `kitty` — '“Tomorrow fortnight.”'
- **pride-and-prejudice** `ch001-u0015` expected `bennet` got `kitty` — '“Then, my dear, you may have the advantage of your friend, and introduce Mr. Bin'
- **pride-and-prejudice** `ch001-u0017` expected `bennet` got `kitty` — '“I honour your circumspection. A fortnight’s acquaintance is certainly very litt'
- **pride-and-prejudice** `ch001-u0019` expected `bennet` got `kitty` — '“What can be the meaning of that emphatic exclamation?” cried he. “Do you consid'
- **sherlock-holmes** `ch001-u0008` expected `holmes` got `ambiguous` — '“Wedlock suits you,” he remarked. “I think, Watson, that you have put\non seven a'
- **sherlock-holmes** `ch001-u0010` expected `holmes` got `john-watson` — '“Indeed, I should have thought a little more. Just a trifle more, I\nfancy, Watso'
- **sherlock-holmes** `ch001-u0012` expected `holmes` got `john-watson` — '“I see it, I deduce it. How do I know that you have been getting\nyourself very w'
- **sherlock-holmes** `ch001-u0015` expected `holmes` got `ambiguous` — '“It is simplicity itself,” said he; “my eyes tell me that on the inside\nof your '
- **sherlock-holmes** `ch001-u0017` expected `holmes` got `john-watson` — '“Quite so,” he answered, lighting a cigarette, and throwing himself\ndown into an'
- **sherlock-holmes** `ch001-u0019` expected `holmes` got `john-watson` — '“How often?”'
- **sherlock-holmes** `ch001-u0021` expected `holmes` got `john-watson` — '“Then how many are there?”'
- **sherlock-holmes** `ch001-u0023` expected `holmes` got `john-watson` — '“Quite so! You have not observed. And yet you have seen. That is just\nmy point. '
- **sherlock-holmes** `ch001-u0025` expected `watson` got `ambiguous` — '“There will call upon you to-night, at a quarter to eight o’clock,” it\nsaid, “a '
- **sherlock-holmes** `ch001-u0027` expected `holmes` got `john-watson` — '“I have no data yet. It is a capital mistake to theorise before one has\ndata. In'
- **treasure-island** `ch001-u0002` expected `long-john-silver` got `jim-hawkins` — '“Yes, my lad,” said he; “such is my name, to be sure. And who may you\nbe?” And t'
- **treasure-island** `ch001-u0003` expected `long-john-silver` got `jim-hawkins` — '“Oh!” said he, quite loud, and offering his hand. “I see. You are our\nnew cabin-'
