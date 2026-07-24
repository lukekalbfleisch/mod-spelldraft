#!/usr/bin/env bash

MOD_SPELLDRAFT_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )/" && pwd )"

source $MOD_SPELLDRAFT_ROOT"/conf/conf.sh.dist"

if [ -f $MOD_SPELLDRAFT_ROOT"/conf/conf.sh" ]; then
    source $MOD_SPELLDRAFT_ROOT"/conf/conf.sh"
fi
