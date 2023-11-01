import dataclasses
import datetime
from bs4 import BeautifulSoup
from tqdm import tqdm
import pickle

import requests
from urllib.parse import quote

cookies = {
    'PHPSESSID': '486hqva34cc5f3tho3jqp4t0tl',
    '_ga': 'GA1.1.1223635531.1698130936',
    '_ga_J1K08MER9S': 'GS1.1.1698130935.1.1.1698130966.0.0.0',
}

# fetch data
sess = requests.Session()
sess.headers = {
    'Accept': 'application/json, text/javascript, */*; q=0.01',
    'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
    'Connection': 'keep-alive',
    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
    'Origin': 'https://gol.gg',
    'Referer': 'https://gol.gg/tournament/list/',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-origin',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/116.0.0.0 Safari/537.36',
    'X-Requested-With': 'XMLHttpRequest',
    'sec-ch-ua': '"Chromium";v="116", "Not)A;Brand";v="24", "Google Chrome";v="116"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
}


@dataclasses.dataclass
class MatchResult:
    season: int
    tournament: dict
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    date: datetime.datetime
    patch: (int, int)


@dataclasses.dataclass
class Team:
    season: str
    name: str
    region: str
    games: int
    win_rate: float


def crawl_teams():
    seasons = [i for i in range(3, 14)]
    all_teams = []

    for s in seasons:
        print(f'processing S{s}')
        r = sess.get(f'https://gol.gg/teams/list/season-S{s}/split-Summer/tournament-ALL/', cookies=cookies)
        soup = BeautifulSoup(r.text, features='lxml')
        for m in soup.select('body > div > main > div:nth-child(5) > div > div:nth-child(3) > div > table > tr'):
            try:
                td_list = m.find_all('td')
                region = td_list[2].text.strip()
                name = td_list[0].text.strip()
                season = td_list[1].text.strip()
                games = int(td_list[3].text.strip())
                win_rate = float(td_list[4].text.strip()[:-1]) / 100
                t = Team(season=season, name=name, region=region, games=games, win_rate=win_rate)
                all_teams.append(t)
            except (Exception,):
                print(f'cannot parse game: {m.text}')

    with open('data/total_teams.pkl', 'wb') as f:
        pickle.dump(all_teams, f)


def crawl_match():
    seasons = [i for i in range(3, 14)]
    all_match = []

    for s in seasons:
        print(f'processing S{s}')
        data = {
            'season': f'S{s}',
        }
        response = sess.post('https://gol.gg/tournament/ajax.trlist.php', cookies=cookies, data=data)
        season_tournaments = response.json()
        for t in tqdm(season_tournaments):
            r = requests.get(f'https://gol.gg/tournament/tournament-matchlist/{quote(t["trname"])}/')
            soup = BeautifulSoup(r.text, features='lxml')
            for m in soup.select_one(
                    'body > div > main > div:nth-child(7) > div > div:nth-child(5) > div > section > '
                    'div > div > table > tbody'):
                try:
                    td_list = m.find_all('td')
                    score = td_list[2].text.strip()
                    if score == '-':
                        continue
                    home_team = td_list[1].text.strip()
                    away_team = td_list[3].text.strip()
                    try:
                        patch = [int(x) for x in td_list[5].text.strip().split('.')]
                    except ValueError:
                        patch = [s, 0]
                    date = datetime.datetime.strptime(td_list[6].text, '%Y-%m-%d')

                    home_score, away_score = score.split('-')
                    # FF stands for forfeit (弃权)
                    if home_score.strip() == 'FF':
                        home_score = 0
                    elif away_score.strip() == 'FF':
                        away_score = 0
                    mr = MatchResult(home_team=home_team, away_team=away_team, home_score=int(home_score),
                                     away_score=int(away_score), date=date, patch=patch, season=s, tournament=t)
                    all_match.append(mr)
                except (Exception,):
                    print(f'cannot parse game: {m.text}')

    with open('data/total_match.pkl', 'wb') as f:
        pickle.dump(all_match, f)


def load_data() -> tuple[list[MatchResult], list[Team]]:
    with open('data/total_match.pkl', 'rb') as f:
        total_match = pickle.load(f)
    with open('data/total_teams.pkl', 'rb') as f:
        total_teams = pickle.load(f)
    total_match.sort(key=lambda x: x.date)
    total_teams.sort(key=lambda x: x.season)
    return total_match, total_teams


if __name__ == '__main__':
    crawl_teams()
