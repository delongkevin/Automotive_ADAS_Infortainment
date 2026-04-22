# -*- coding: utf-8 -*-
#  Copyright (c) 2020. MAGNA Electronics - S T R I C T L Y  C O N F I D E N T I A L
#  This document in its entirety is STRICTLY CONFIDENTIAL and may not be
#  disclosed, disseminated or distributed to parties outside MAGNA
#  Electronics without written permission from MAGNA Electronics.
#

# pylint: disable=invalid-name


import os

import libs.PyCP210x as PyCP210x

INITIALIZED = False


def init():
    global INITIALIZED  # pylint: disable=global-statement

    if not INITIALIZED:  # pragma: no cover
        INITIALIZED = PyCP210x.init(os.path.dirname(__file__))  # pylint: disable=c-extension-no-member # pragma: no cover
        # These Cases are cover with a unittest but the coverage report is not reflecting this,
        # because of the library use within this module
        if not INITIALIZED:  # pragma: no cover
            raise BaseException("Py2CP210x initialization failed!")

        INITIALIZED = True  # pragma: no cover
