"""Synthetic-only history checks: execution, causal signals and fixed selection."""
import numpy as np
import pandas as pd
import pytest

from moowoo import data
from moowoo.history import bootstrap, evaluate, simulate_trade
from moowoo.indicators import abnormal_move_z, move_z
from moowoo.screener import screen


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError('network forbidden')
    monkeypatch.setattr(data.yf, 'Ticker', blocked)


def market(n=90):
    rng = np.random.default_rng(7)
    close = 100*np.cumprod(1+rng.normal(0, .005, n))
    return pd.DataFrame(dict(open=close, high=close+1, low=close-1,
                             close=close, volume=1e6), index=pd.bdate_range('2024-01-01', periods=n))


def test_exact_market_tracker_is_zero_despite_raw_shock():
    spy = market()
    spy.iloc[-1, spy.columns.get_loc('close')] = spy.close.iloc[-2]*1.15
    spy.iloc[-1, spy.columns.get_loc('open')] = spy.close.iloc[-2]*1.12
    stock = spy.copy()
    assert move_z(stock)['z'] > 10
    assert abnormal_move_z(stock, spy)['z'] == 0
    assert abnormal_move_z(stock, spy)['beta'] == pytest.approx(1)
    assert screen({'passing': ['A']}, stock.index[-1], bars={'A': stock, 'SPY': spy},
                  earnings={}, mode='raw')['picked'] == ['A']
    assert screen({'passing': ['A']}, stock.index[-1], bars={'A': stock, 'SPY': spy},
                  earnings={}, mode='abnormal')['picked'] == []
    assert screen({'passing': ['A']}, stock.index[-1], bars={'A': stock, 'SPY': spy},
                  earnings={})['picked'] == []


def test_ols_parameters_exclude_signal_day_and_match_prior_fit():
    spy, stock = market(), market()
    stock['close'] *= 1 + np.sin(np.arange(len(stock)))*.003
    before = abnormal_move_z(stock, spy)
    x = spy.close.pct_change().iloc[-61:-1].to_numpy()
    y = stock.close.pct_change().iloc[-61:-1].to_numpy()
    beta, intercept = np.linalg.lstsq(np.column_stack([x, np.ones(60)]), y, rcond=None)[0]
    assert before['beta'] == pytest.approx(beta)
    assert before['sigma'] == pytest.approx(np.sqrt(np.sum((y-intercept-beta*x)**2)/58))
    stock.iloc[-1, stock.columns.get_loc('close')] *= 2
    spy.iloc[-1, spy.columns.get_loc('close')] *= .5
    after = abnormal_move_z(stock, spy)
    assert after['beta'] == before['beta']
    assert after['sigma'] == before['sigma']


@pytest.mark.parametrize('mode', ['raw', 'abnormal'])
def test_future_bar_does_not_change_past_screen(mode):
    spy, stock = market(), market()
    stock['close'] *= 1+np.sin(np.arange(len(stock)))*.002
    date = stock.index[-2]
    stock.loc[date, 'open'] *= 1.1
    before = screen({'passing': ['A']}, date, bars={'A': stock, 'SPY': spy}, earnings={}, mode=mode)
    assert before['picked'] == ['A']
    stock.iloc[-1] = [1, 1e5, .1, 100, 1e10]
    spy.iloc[-1] = [1, 1e5, .1, 100, 1e10]
    after = screen({'passing': ['A']}, date, bars={'A': stock, 'SPY': spy}, earnings={}, mode=mode)
    assert before == after


def execution_frame():
    return pd.DataFrame(dict(open=[90, 100, 100, 100, 100, 100, 100],
                             high=[91, 101, 101, 101, 101, 101, 101],
                             low=[89, 99, 99, 99, 99, 99, 99],
                             close=[90, 100, 100, 100, 100, 100, 100], volume=1e6),
                        index=pd.bdate_range('2024-01-01', periods=7))


def context(**kwargs):
    return dict(dict(atr=2, support=None, target=105, score=3), **kwargs)


def test_entry_next_open_and_five_session_time_exit():
    df = execution_frame()
    trade = simulate_trade(df, df, df.index[0], context(), 'drift', 2)
    assert trade['entry'] == 100
    assert trade['entryDate'] == str(df.index[1].date())
    assert trade['exitDate'] == str(df.index[5].date())
    assert trade['reason'] == 'time'
    assert trade['returnNet'] == pytest.approx(.9995/1.0005-1)


def test_stop_first_when_target_and_stop_in_bar():
    df = execution_frame()
    df.loc[df.index[1], ['low', 'high']] = [95, 106]
    trade = simulate_trade(df, df, df.index[0], context(), 'bounce', 2)
    assert trade['reason'] == 'stop'
    assert trade['exit'] == 96


def test_bounce_target_exit():
    df = execution_frame()
    df.loc[df.index[2], 'high'] = 106
    trade = simulate_trade(df, df, df.index[0], context(), 'bounce', 2)
    assert trade['reason'] == 'target'
    assert trade['exit'] == 105
    assert trade['exitDate'] == str(df.index[2].date())


def test_trail_rises_only_and_activates_following_bar():
    df = execution_frame()
    df.loc[df.index[1], ['open', 'high', 'low', 'close']] = [100, 104, 98, 103]
    df.loc[df.index[2], ['open', 'high', 'low', 'close']] = [103, 105, 101, 104]
    df.loc[df.index[3], ['open', 'high', 'low', 'close']] = [103, 104, 102, 102]
    df.loc[df.index[4], ['open', 'high', 'low', 'close']] = [102, 103, 100, 102]
    trade = simulate_trade(df, df, df.index[0], context(), 'drift', 2)
    assert trade['stops'] == [96, 100, 101, 101]
    assert trade['exit'] == 101
    assert trade['exitDate'] == str(df.index[4].date())


def test_gap_through_stop_fills_open_and_period_end_is_censored():
    df = execution_frame()
    df.loc[df.index[1], 'open'] = 100
    df.loc[df.index[2], ['open', 'low']] = [90, 89]
    trade = simulate_trade(df, df, df.index[0], context(), 'drift', 2)
    assert trade['exit'] == 90
    assert simulate_trade(df.iloc[:4], df, df.index[0], context(), 'drift', 2) is None


def test_bootstrap_deterministic():
    values = [-.03, .01, .02, .04]
    assert bootstrap(values, 17) == bootstrap(values, 17)
    assert bootstrap([.02]*10) == pytest.approx([.02, .02])
    assert bootstrap([]) is None


def test_missing_next_session_does_not_delay_entry():
    spy = execution_frame()
    stock = spy.drop(spy.index[1])
    assert simulate_trade(stock, spy, spy.index[0], context(), 'bounce', 2) is None


def test_selection_does_not_use_holdout():
    names = ['follow-all', 'fade-all', 'drift-2', 'drift-2.5', 'drift-3', 'bounce-2', 'bounce-2.5']
    def trade(excess):
        return dict(returnNet=excess, excess=excess, spyReturn=0, score=3, rvol=2)
    pools = {mode: {p: {name: [trade(.01 if mode == 'raw' else .02)]*100 for name in names}
                    for p in ('FIT', 'HOLDOUT')} for mode in ('raw', 'abnormal')}
    first, _ = evaluate(pools)
    assert first['chosen']['parameters']['MOVE_MODE'] == 'abnormal'
    for name in names:
        pools['raw']['HOLDOUT'][name] = [trade(.9)]*100
        pools['abnormal']['HOLDOUT'][name] = [trade(-.9)]*100
    second, _ = evaluate(pools)
    assert first['chosen']['id'] == second['chosen']['id']
    pools['raw']['FIT']['bounce-2'] = []
    pools['raw']['FIT']['bounce-2.5'] = []
    pools['abnormal']['FIT']['bounce-2'] = []
    pools['abnormal']['FIT']['bounce-2.5'] = []
    result, _ = evaluate(pools)
    assert result['chosen'] is None
