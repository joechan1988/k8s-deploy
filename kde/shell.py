#!/usr/bin/python
# -*- coding: utf-8 -*-
import os
import sys
import logging
import argparse
from util import common, config_parser, exception
from cmd import deploy
from templates import constants


# log_level = common.get_log_level("")
# logging.basicConfig(level=logging.CRITICAL,
#                     format='%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s',
#                     datefmt='%a, %d %b %Y %H:%M:%S',
#                     )


class Subcommands(object):
    def __init__(self):
        pass

    # @common.arg('--config', default=constants.cluster_cfg_path, help="Default config file path")
    @common.cmd_help('Deploy a initiated kubernetes cluster according to cluster.yml')
    def deploy(self, args, **cluster_data):
        # configs = config_parser.Config(args.config)
        # configs.load()
        # cluster_data = configs.data
        #
        # deploy.do(cluster_data)
        # logging.critical("do func deploy " + args.config)
        results = dict()
        try:
            results = deploy.do(cluster_data)
        except exception.BaseError as e:
            logging.critical(e.message)

        logging.critical(results)

    @common.cmd_help("Reset the last cluster deployment")
    def reset(self, args, **cluster_data):

        deploy.reset(**cluster_data)

    # @common.arg('--config', default=constants.cluster_cfg_path, help="Default config file path")
    def test(self, args):
        print(args.config)


def _get_funcs(obj):
    result = []
    for i in dir(obj):
        if callable(getattr(obj, i)) and not i.startswith('_'):
            result.append((i, getattr(obj, i)))
    return result


def _set_log_level(level_str):
    log_level = common.get_log_level(level_str)
    logging.basicConfig(level=log_level,
                        format='%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s',
                        datefmt='%a, %d %b %Y %H:%M:%S',
                        )


def _parse_cluster_data(config_path):
    configs = config_parser.Config(config_path)
    configs.load()
    return configs.data


def main():
    # Arguments
    top_parser = argparse.ArgumentParser()
    top_parser.add_argument('--test', dest='test_unit', type=str, default='')
    top_parser.add_argument('--config', type=str, default=constants.cluster_cfg_path)

    # Subcommands
    subparsers = top_parser.add_subparsers(help='Commands')
    subcommands_obj = Subcommands()
    subcommands = _get_funcs(subcommands_obj)

    for (func_name, func) in subcommands:
        try:
            func_help = getattr(func, 'help')
        except AttributeError as e:
            func_help = ""

        func_parser = subparsers.add_parser(func_name, help=func_help)
        func_parser.set_defaults(func=func)

        for args, kwargs in getattr(func, 'arguments', []):
            func_parser.add_argument(*args, **kwargs)

    # parser_deploy = subparsers.add_parser('deploy', help='Deploy Kubernetes')

    # parser_deploy.set_defaults(func=deploy)

    # parser_test = subparsers.add_parser('test', help='Run Tests')
    # for args, kwargs in getattr(test, 'arguments', []):
    #     parser_test.add_argument(*args, **kwargs)
    # parser_test.set_defaults(func=test)

    top_args = top_parser.parse_args()

    # Parse cluster config file
    cluster_data = _parse_cluster_data(top_args.config)

    # Set log level
    _set_log_level(cluster_data.get('log_level'))

    top_args.func(top_args, **cluster_data)


if __name__ == "__main__":
    main()