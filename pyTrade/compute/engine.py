from algorithms import *

import ipdb as pdb
import sys
import os
import argparse
import json

sys.path.append(os.environ['QTRADE'])
from pyTrade.data.datafeed import DataFeed
from logbook import Logger
#from pyTrade.utils.LogSubsystem import LogSubsystem
from pyTrade.ai.manager import equity, optimal_frontier

import pytz
import pandas as pd
import numpy as np

from qstkutil import tsutil as tsu

#from zipline.data.benchmarks import *


class BacktesterEngine(object):
    ''' Factory class wrapping zipline Backtester, returns the requested algo '''
    algos = {'DualMA'      : DualMovingAverage       , 'Momentum'   : Momentum,
             'VWAP'        : VolumeWeightAveragePrice, 'BuyAndHold' : BuyAndHold,
             'StdBased' : StddevBased             , 'OLMAR'      : OLMAR,
             'MultiMA'     : MultiMA                 , 'MACrossover': MovingAverageCrossover}

    portfolio_strategie = {'Equity': equity, 'OptimalFrontier': optimal_frontier}

    def __new__(self, algo, manager, algo_params, pf_params):
        if algo not in BacktesterEngine.algos:
            raise NotImplementedError('Algorithm {} not available or implemented'.format(algo))
        print('[Debug] Algorithm {} available, getting a reference to it.'.format(algo))
        if manager not in BacktesterEngine.portfolio_strategie:
            raise NotImplementedError('Manager {} not available or implemented'.format(manager))
        print('[Debug] Manager {} available, getting a reference to it.'.format(manager))
        return BacktesterEngine.algos[algo](algo_params, BacktesterEngine.portfolio_strategie[manager], pf_params)


class Simulation(object):
    ''' Take a trading strategie and evalute its results '''
    def __init__(self, flavor='mysql', lvl='debug'):
        #NOTE Allowing different data access ?
        #self.log          = LogSubsystem('Simulation', lvl).getLog()
        self.log           = Logger(self.__class__.__name__)
        self.feeds         = DataFeed()
        self.backtest_cfg  = None
        self.algo_cfg      = None
        self.manager_cfg   = None
        self.monthly_perfs = None

    def read_config(self, bt_cfg=None, a_cfg=None, m_cfg=None, bt_root=None):
        ''' Reads and provides a clean configuration for the simulation '''
        if not bt_root:
            bt_root = os.environ['QTRADE'] + '/backtester/'

        if not bt_cfg:
            parser = argparse.ArgumentParser(description='Backtester module, the terrific financial simukation')
            parser.add_argument('-v', '--version', action='version', version='%(prog)s v0.8.1 Licence rien du tout', help='Print program version')
            parser.add_argument('-d', '--delta', type=int, action='store', default=1, required=False, help='Delta in days betweend two quotes fetch')
            parser.add_argument('-a', '--algorithm', action='store', required=True, help='Trading algorithm to be used')
            parser.add_argument('-m', '--manager', action='store', required=True, help='Portfolio strategie to be used')
            parser.add_argument('-b', '--database', action='store', default='stocks.db', required=False, help='Database location')
            parser.add_argument('-l', '--level', action='store', default='debug', required=False, help='Verbosity level')
            parser.add_argument('-t', '--tickers', action='store', required=True, help='target names to process')
            parser.add_argument('-s', '--start', action='store', default='1/1/2006', required=False, help='Start date of the backtester')
            parser.add_argument('-e', '--end', action='store', default='1/12/2010', required=False, help='Stop date of the backtester')
            parser.add_argument('-i', '--interactive', action='store_true', help='Indicates if the program was ran manually or not')
            args = parser.parse_args()

            self.backtest_cfg = {'algorithm'   : args.algorithm,
                                 'delta'       : args.delta,
                                 'manager'     : args.manager,
                                 'database'    : args.database,
                                 'level'       : args.level,
                                 'tickers'     : args.tickers.split(','),
                                 'start'       : args.start,
                                 'end'         : args.end,
                                 'interactive' : args.interactive}
        else:
            bt_cfg['tickers'] = bt_cfg['tickers'].split(',')
            self.backtest_cfg = bt_cfg

        if isinstance(self.backtest_cfg['start'], str) and isinstance(self.backtest_cfg['end'], str):
            self.backtest_cfg['start'] = pytz.utc.localize(pd.datetime.strptime(self.backtest_cfg['start'], '%Y-%m-%d'))
            self.backtest_cfg['end']   = pytz.utc.localize(pd.datetime.strptime(self.backtest_cfg['end'], '%Y-%m-%d'))
        elif isinstance(self.backtest_cfg['start'], dt.datetime) and isinstance(self.backtest_cfg['end'], dt.datetime):
            raise NotImplementedError()
        else:
            raise NotImplementedError()

        try:
            if self.backtest_cfg['interactive']:
                if a_cfg:
                    self.algo_cfg = a_cfg
                else:
                    self.algo_cfg    = json.load(open('{}/algos.cfg'.format(bt_root), 'r'))[self.backtest_cfg['algorithm']]
                if m_cfg:
                    self.manager_cfg = m_cfg
                else:
                    self.manager_cfg = json.load(open('{}/managers.cfg'.format(bt_root), 'r'))[self.backtest_cfg['manager']]
            else:
                self.algo_cfg    = json.loads(raw_input('algo >'))
                self.manager_cfg = json.loads(raw_input('manager >'))
                #algo_cfg_str    = raw_input('algo > ')
                #manager_cfg_str = raw_input('manager > ')
                #self.algo_cfg    = json.loads(algo_cfg_str)
                #self.manager_cfg = json.loads(manager_cfg_str)
        except:
            self.log.error('** loading json configuration.')
            sys.exit(1)

        return self.backtest_cfg

    def runBacktest(self):
        if self.backtest_cfg is None or self.algo_cfg is None or self.manager_cfg is None:
            self.log.error('** Backtester not configured properly')
            return 1

        '''--------------------------------------------    Parameters    -----'''
        if self.backtest_cfg['tickers'][0] == 'random':
            assert(len(self.backtest_cfg['tickers']) == 2)
            assert(int(self.backtest_cfg['tickers'][1]))
            self.backtest_cfg['tickers'] = self.feeds.random_stocks(int(self.backtest_cfg['tickers'][1]))

        data = self.feeds.quotes(self.backtest_cfg['tickers'],
                                 start_date = self.backtest_cfg['start'],
                                 end_date   = self.backtest_cfg['end'])
        assert isinstance(data, pd.DataFrame)
        assert data.index.tzinfo

        '''-----------------------------------------------    Running    -----'''
        self.log.info('\n-- Running backetester...\nUsing algorithm: {}\n'.format(self.backtest_cfg['algorithm']))
        self.log.info('\n-- Using portfolio manager: {}\n'.format(self.backtest_cfg['manager']))

        backtester = BacktesterEngine(self.backtest_cfg['algorithm'],
                                      self.backtest_cfg['manager'],
                                      self.algo_cfg,
                                      self.manager_cfg)
        self.results, self.monthly_perfs = backtester.run(data,
                                                          self.backtest_cfg['start'],
                                                          self.backtest_cfg['end'])

        return self.results

    def rolling_performances(self, timestamp='one_month', save=False, db_id=None):
        ''' Filters self.perfs and, if asked, save it to database '''
        #TODO Study the impact of month choice
        #TODO Check timestamp in an enumeration

        if db_id is None:
            db_id = self.backtest_cfg['algorithm'] + pd.datetime.strftime(pd.datetime.now(), format='%Y%m%d')

        if self.monthly_perfs:
            perfs  = dict()
            length = range(len(self.monthly_perfs[timestamp]))
            index  = self._get_index(self.monthly_perfs[timestamp])
            perfs['Name']                 = np.array([db_id] * len(self.monthly_perfs[timestamp]))
            #perfs['Period']               = np.array([self.monthly_perfs[timestamp][i]['period_label'] for i in length])
            perfs['Period']               = np.array([pd.datetime.date(date)                                      for date in index])
            perfs['Sharpe.Ratio']         = np.array([self.monthly_perfs[timestamp][i]['sharpe']                  for i in length])
            perfs['Returns']              = np.array([self.monthly_perfs[timestamp][i]['algorithm_period_return'] for i in length])
            perfs['Max.Drawdown']         = np.array([self.monthly_perfs[timestamp][i]['max_drawdown']            for i in length])
            perfs['Volatility']           = np.array([self.monthly_perfs[timestamp][i]['algo_volatility']         for i in length])
            perfs['Beta']                 = np.array([self.monthly_perfs[timestamp][i]['beta']                    for i in length])
            perfs['Alpha']                = np.array([self.monthly_perfs[timestamp][i]['alpha']                   for i in length])
            perfs['Excess.Returns']       = np.array([self.monthly_perfs[timestamp][i]['excess_return']           for i in length])
            perfs['Benchmark.Returns']    = np.array([self.monthly_perfs[timestamp][i]['benchmark_period_return'] for i in length])
            perfs['Benchmark.Volatility'] = np.array([self.monthly_perfs[timestamp][i]['benchmark_volatility']    for i in length])
            perfs['Treasury.Returns']     = np.array([self.monthly_perfs[timestamp][i]['treasury_period_return']  for i in length])
        else:
            #TODO Get it from DB if it exists
            raise NotImplementedError()

        try:
            data = pd.DataFrame(perfs, index=index)
        except:
            pdb.set_trace()

        if save:
            self.feeds.stock_db.save_metrics(data)
        return data

    def overall_metrics(self, timestamp='one_month', save=False, db_id=None):
        ''' Use zipline results to compute some performance indicators and store it in database '''
        perfs = dict()
        metrics = self.rolling_performances(timestamp=timestamp, save=False, db_id=db_id)
        riskfree = np.mean(metrics['Treasury.Returns'])

        if db_id is None:
            db_id = self.algorithm + pd.datetime.strftime(pd.datetime.now(), format='%Y%m%d')
        perfs['Name']              = db_id
        perfs['Sharpe.Ratio']      = tsu.get_sharpe_ratio(metrics['Returns'].values, risk_free = riskfree)
        perfs['Returns']           = (((metrics['Returns'] + 1).cumprod()) - 1)[-1]
        perfs['Max.Drawdown']      = min(metrics['Max.Drawdown'])
        perfs['Volatility']        = np.mean(metrics['Volatility'])
        perfs['Beta']              = np.mean(metrics['Beta'])
        perfs['Alpha']             = np.mean(metrics['Alpha'])
        perfs['Benchmark.Returns'] = (((metrics['Benchmark.Returns'] + 1).cumprod()) - 1)[-1]

        if save:
            self.feeds.stock_db.save_performances(perfs)
        return perfs

    #TODO Rewrite
    def get_returns(self, freq=pd.datetools.BDay(), benchmark=False, timestamp='one_month', save=False, db_id=None):
        df = pd.DataFrame()
        returns = dict()

        returns['Benchmark.Returns']  = self._extract_perf(self.monthly_perfs[timestamp], 'benchmark_period_return')
        returns['Benchmark.CReturns'] = ((perfs['Benchmark.Returns'] + 1).cumprod()) - 1
        returns['Returns']            = self._extract_perf(self.monthly_perfs[timestamp], 'algorithm_period_return')
        returns['CReturns']           = ((perfs['algo_rets'] + 1).cumprod()) - 1

        df = pd.DataFrame(perfs, index=perfs['Returns'].index)

        if save:
            self.feeds.saveDFToDB(df, table_name=db_id)
        return df

    def _get_index(self, perfs):
        #NOTE No frequency infos or just period number ?
        start = pytz.utc.localize(pd.datetime.strptime(perfs[0]['period_label'] + '-01', '%Y-%m-%d'))
        end = pytz.utc.localize(pd.datetime.strptime(perfs[-1]['period_label'] + '-01', '%Y-%m-%d'))
        return pd.date_range(start - pd.datetools.BDay(10), end, freq=pd.datetools.BMonthBegin())

    def _extract_perf(self, perfs, field):
        index = self._get_index(perfs)
        values = [perfs[i][field] for i in range(len(perfs))]
        return pd.Series(values, index=index)