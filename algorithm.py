from typing import Callable

from data_reader import load_data, Team, MatchResult
import math
import datetime
import matplotlib.pyplot as plt
import matplotlib
import pandas as pd
import trueskill
from tqdm import tqdm
import functools
import trueskillthroughtime as ttt

matplotlib.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams["figure.facecolor"] = 'white'
plt.rcParams["figure.dpi"] = 300

total_match, total_teams = load_data()


def get_match_weight(match: MatchResult, current_season: int, current_date: datetime.datetime,
                     season_decay_factor: float = 0.5,
                     date_half_life: float = 365) -> float:
    mn = match.tournament['trname']
    if 'LCK CL' in mn or 'LPLOL' in mn:
        tournament_weight = 0.1
    elif 'World Championship' in mn or 'Worlds' in mn:
        if 'play-in' in mn.lower() or 'playin' in mn.lower():
            tournament_weight = 5
        else:
            tournament_weight = 10
    elif 'MSI' in mn:
        if 'play-in' in mn.lower() or 'playin' in mn.lower():
            tournament_weight = 3
        else:
            tournament_weight = 6
    # elif 'WR' == match.tournament['region']:
    #     tournament_weight = 2
    elif any(x in mn for x in ['LPL', 'OGN', 'LCK']):
        if 'playoffs' in mn.lower() or 'final' in mn.lower():
            tournament_weight = 3
        else:
            tournament_weight = 1.5
    elif any(x in mn for x in ['LEC', 'LCS']):
        if 'playoffs' in mn.lower() or 'final' in mn.lower():
            tournament_weight = 2
        else:
            tournament_weight = 1
    elif any(x in mn for x in ['PCS', 'VCS', 'LMS']):
        if 'playoffs' in mn.lower() or 'final' in mn.lower():
            tournament_weight = 1
        else:
            tournament_weight = 0.5
    else:
        tournament_weight = 0.2

    season_decay = season_decay_factor ** (current_season - match.season)
    # season_decay = 1
    date_factor = math.exp((match.date - current_date).days / date_half_life)
    # date_factor = 1

    bo_score = 1
    # bo_score = max(match.home_score, match.away_score, 1)
    return season_decay * date_factor * tournament_weight * bo_score


def normalize_team_name(team_name: str) -> str:
    m_all = {
        'DAMWON Gaming': 'Dplus KIA',
        'DWG KIA': 'Dplus KIA',
        # 'DK Challengers': 'DWG KIA',
        'Samsung Galaxy White': 'Gen.G',
        'Samsung Galaxy': 'Gen.G',
        'Samsung Galaxy Blue': 'Gen.G',
        'Gen.G eSports': 'Gen.G',
        'SKTelecom T1': 'T1',
        'SK Telecom T1': 'T1',
        'SK Telecom T1 K': 'T1',
        'Qiao Gu': 'QG',
        'Qiao Gu Reapers': 'QG',
        'Victory Five': 'Ninjas in Pyjamas'
    }
    m = {
        'SKTelecom T1': 'SK Telecom T1'
    }
    return m.get(team_name, team_name)


@functools.lru_cache(maxsize=100, typed=False)
def get_team_region(team_name: str, season: str = None) -> str:
    for t in total_teams:
        if t.name == team_name and (season is None or season == t.season):
            return t.region
    return 'UNK'


def calculate_elo(match_results: list[MatchResult],
                  initial_ratings: dict[str, float] = None, initial_variances: dict[str, float] = None,
                  plot: str = None):
    if not initial_ratings:
        team_ratings = {}
    else:
        team_ratings = initial_ratings

    if not initial_variances:
        team_variances = {}
    else:
        team_variances = initial_variances

    team_highest_ratings = {}  # 新增：保存每个队伍的历史最高分数

    team_matches = {}  # 过滤掉比赛数过少的队伍
    current_season = match_results[-1].season
    current_date = match_results[-1].date

    for match in match_results:
        home_team = normalize_team_name(match.home_team)
        away_team = normalize_team_name(match.away_team)

        team_matches[home_team] = team_matches.get(home_team, 0) + 1
        team_matches[away_team] = team_matches.get(away_team, 0) + 1

        if home_team not in team_ratings:
            team_ratings[home_team] = 1500
            team_variances[home_team] = 25

        if away_team not in team_ratings:
            team_ratings[away_team] = 1500
            team_variances[away_team] = 25

    for match in match_results:
        home_team = normalize_team_name(match.home_team)
        away_team = normalize_team_name(match.away_team)
        home_score = match.home_score
        away_score = match.away_score

        rating1 = team_ratings[home_team]
        rating2 = team_ratings[away_team]
        variance1 = team_variances[home_team]
        variance2 = team_variances[away_team]

        diff = rating1 - rating2
        probability = 1 / (1 + math.exp(-diff / 400))

        match_weight = get_match_weight(match, current_season, current_date)

        if home_score > away_score:
            team_ratings[home_team] += variance1 * (1 - probability) * match_weight
            team_ratings[away_team] -= variance2 * (1 - probability) * match_weight
        else:
            team_ratings[home_team] -= variance1 * probability * match_weight
            team_ratings[away_team] += variance2 * probability * match_weight

        # 保存每个队伍的历史最高分数和对应日期
        home_highest_rating, home_highest_date = team_highest_ratings.get(home_team, (0, None))
        away_highest_rating, away_highest_date = team_highest_ratings.get(away_team, (0, None))

        if team_ratings[home_team] > home_highest_rating:
            team_highest_ratings[home_team] = (team_ratings[home_team], match.date)

        if team_ratings[away_team] > away_highest_rating:
            team_highest_ratings[away_team] = (team_ratings[away_team], match.date)

    ret = sorted(team_ratings.items(), key=lambda x: x[1], reverse=True)
    ret = [(team, rating) for team, rating in ret if team_matches[team] >= 5]

    if plot:
        plot_team_rating(ret, plot)
        highest = sorted(team_highest_ratings.items(), key=lambda x: x[1], reverse=True)
        highest = [(f'{team}-{rating[1].strftime("%y-%m")}', rating[0]) for team, rating in highest if
                   team_matches[team] >= 5]
        plot_team_rating(highest, plot + '-highest')

    return ret, team_ratings, team_variances


def plot_team_rating(ratings: list[tuple[str, float]], save_path: str, top_k: int = 15):
    teams = [t for t, _ in ratings[:top_k]]
    ratings = [r for _, r in ratings[:top_k]]

    # 创建柱状图
    plt.figure(figsize=(12, 6))
    plt.bar(teams, ratings)

    # 添加图表标题和坐标轴标签
    plt.title('Top 10 Rating')
    plt.xlabel('Team')
    plt.ylabel('ELO Rating')

    # 旋转x轴刻度标签，使其易于阅读
    plt.xticks(rotation=25)
    plt.title('ELO')
    # 显示图表
    if save_path:
        plt.savefig(save_path)
    plt.close()


# noinspection PyUnresolvedReferences
def calculate_trueskill(match_results: list[MatchResult], plot: str = None):
    # 初始化TrueSkill环境
    ts = trueskill.TrueSkill(draw_probability=0)

    team_ratings = {}

    team_matches = {}  # 过滤掉比赛数过少的队伍

    # 添加比赛数据
    for match in match_results:
        home_team = normalize_team_name(match.home_team)
        away_team = normalize_team_name(match.away_team)
        home_score = match.home_score
        away_score = match.away_score
        # 获取或创建队伍的TrueSkill评级
        if home_team not in team_ratings:
            team_ratings[home_team] = ts.create_rating()
        if away_team not in team_ratings:
            team_ratings[away_team] = ts.create_rating()

        team_matches[home_team] = team_matches.get(home_team, 0) + 1
        team_matches[away_team] = team_matches.get(away_team, 0) + 1

        final_factor = get_match_weight(match, match_results[-1].season, match_results[-1].date)
        ts.sigma *= final_factor

        # 更新队伍的TrueSkill评级
        if home_score > away_score:
            team_ratings[home_team], team_ratings[away_team] = ts.rate_1vs1(team_ratings[home_team],
                                                                            team_ratings[away_team])
        else:
            team_ratings[away_team], team_ratings[home_team] = ts.rate_1vs1(team_ratings[away_team],
                                                                            team_ratings[home_team])
        ts.sigma /= final_factor

    ret = sorted(team_ratings.items(), key=lambda x: x[1].mu, reverse=True)
    ret = [(team, rating.mu) for team, rating in ret if team_matches[team] >= 5]
    if plot:
        plot_team_rating(ret, plot)
    return ret


def calculate_ttt(match_results: list[MatchResult], plot: str = None):
    team_ratings = {}
    team_matches = {}  # 过滤掉比赛数过少的队伍

    # 添加比赛数据
    composition = []
    for match in match_results:
        home_team = normalize_team_name(match.home_team)
        away_team = normalize_team_name(match.away_team)
        home_score = match.home_score
        away_score = match.away_score
        # 获取或创建队伍的TrueSkill评级
        # if home_team not in team_ratings:
        #     team_ratings[home_team] = ttt.Player()
        # if away_team not in team_ratings:
        #     team_ratings[away_team] = ttt.Player()

        team_matches[home_team] = team_matches.get(home_team, 0) + 1
        team_matches[away_team] = team_matches.get(away_team, 0) + 1

        # # 更新队伍的TrueSkill评级
        if home_score > away_score:
            # game = ttt.Game([home_team, away_team])
            game = [[home_team], [away_team]]
        else:
            # game = ttt.Game([away_team, home_team])
            game = [[away_team], [home_team]]

        composition.append(game)
    h = ttt.History(composition)
    h.learning_curves()
    return h

    # ret = sorted(team_ratings.items(), key=lambda x: x[1].mu, reverse=True)
    # ret = [(team, rating.mu) for team, rating in ret if team_matches[team] >= 5]
    # if plot:
    #     plot_team_rating(ret, plot)
    # return ret


def main(algorithm: Callable, history: bool = False):
    if history:
        snapshot_records = []

        cur_date = total_match[0].date
        end_date = total_match[-1].date
        days_gap = 14
        last_date_match_count = -1
        with tqdm() as pbar:
            while cur_date < end_date + datetime.timedelta(days=days_gap):
                cur_match = [x for x in total_match if x.date <= cur_date]
                if len(cur_match) == last_date_match_count:
                    cur_date += datetime.timedelta(days=days_gap)
                    pbar.update(1)
                    continue
                last_date_match_count = len(cur_match)
                sorted_ratings, _, _ = algorithm(cur_match)

                for team, rating in sorted_ratings[:50]:
                    region = get_team_region(team)
                    if region != 'UNK':
                        snapshot_records.append(
                            {'name': team, 'value': rating, 'timestamp': cur_match[-1].date.timestamp(),
                             'date': cur_match[-1].date.strftime("%y-%m-%d"),
                             'type': region})
                cur_date += datetime.timedelta(days=days_gap)
                pbar.update(1)

        df = pd.DataFrame(snapshot_records)
        df.to_csv('data/visualization.csv', index=False)
    algorithm(total_match, plot='plot/result')


if __name__ == '__main__':
    main(calculate_elo, True)
