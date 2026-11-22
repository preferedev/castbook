# Castbook attribution eval
_2026-11-22T17:43:39+00:00Z — llamacpp:Qwen3-4B-Instruct-2507-Q4_K_M_

| book | units | labeled | correct | accuracy | ambiguous |
|---|---|---|---|---|---|
| alice-in-wonderland | 146 | 21 | 19 | 90% | 0 |
| dorian-gray | 21 | 16 | 16 | 100% | 0 |
| dr-jekyll-and-mr-hyde | 28 | 20 | 19 | 95% | 0 |
| great-expectations | 46 | 34 | 34 | 100% | 0 |
| huckleberry-finn | 27 | 20 | 15 | 75% | 0 |
| jane-eyre | 26 | 20 | 20 | 100% | 0 |
| moby-dick | 36 | 20 | 20 | 100% | 0 |
| pride-and-prejudice | 34 | 20 | 18 | 90% | 0 |
| sherlock-holmes | 36 | 29 | 25 | 86% | 0 |
| treasure-island | 35 | 25 | 25 | 100% | 0 |

## Misses

- **alice-in-wonderland** `ch006-u0005` expected `ambiguous` got `hatter` — 'The table was a large one, but the three were all crowded together at one corner'
- **alice-in-wonderland** `ch006-u0018` expected `alice` got `narrator` — '“Come, we shall have some fun now!” thought Alice.'
- **dr-jekyll-and-mr-hyde** `ch001-u0027` expected `mr.-enfield` got `the young man` — 'Mr. Utterson sighed deeply but said never a word; and the young man\npresently re'
- **huckleberry-finn** `ch008-u0001` expected `huckleberry-finn` got `narrator` — '“Hello, Jim!” and skipped out.'
- **huckleberry-finn** `ch008-u0013` expected `jim` got `huckleberry finn` — '“Yes—indeedy.”'
- **huckleberry-finn** `ch008-u0014` expected `huckleberry-finn` got `jim` — '“And ain’t you had nothing but that kind of rubbage to eat?”'
- **huckleberry-finn** `ch008-u0017` expected `jim` got `huckleberry finn` — '“I reck’n I could eat a hoss. I think I could. How long you ben on de\nislan’?”'
- **huckleberry-finn** `ch008-u0018` expected `huckleberry-finn` got `jim` — '“Since the night I got killed.”'
- **pride-and-prejudice** `ch001-u0014` expected `kitty` got `elizabeth` — '“When is your next ball to be, Lizzy?”'
- **pride-and-prejudice** `ch001-u0017` expected `bennet` got `elizabeth` — '“Then, my dear, you may have the advantage of your friend, and introduce Mr. Bin'
- **sherlock-holmes** `ch001-u0022` expected `holmes` got `john watson` — '“How often?”'
- **sherlock-holmes** `ch001-u0024` expected `holmes` got `john watson` — '“Then how many are there?”'
- **sherlock-holmes** `ch001-u0030` expected `watson` got `narrator` — '“There will call upon you to-night, at a quarter to eight o’clock,” it\nsaid, “a '
- **sherlock-holmes** `ch001-u0033` expected `holmes` got `john watson` — '“I have no data yet. It is a capital mistake to theorise before one has\ndata. In'
