import numpy as np
# import matlab.engine
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from typing import Tuple, Dict

import time
import math
import numpy as np

from loads import EdgeCrack, DoubleEdgeCrack, CompactTension
from constraints import DensityConstraint
from fesolvers import FESolver, CvxFEA, CGFEA
from topopt import Topopt
from plotting import Plot

def evaluate_llm_response(llm_response):
    """
    Evaluate the LLM response for a topology optimization task based on a predefined rubric.

    Parameters:
    - llm_response: An object with structure matching ConfigFile.

    Returns:
    - passed (bool): Whether the design passed all hard constraints.
    - details (dict): Detailed score breakdown and possible errors.
    - score (int): Total score based on the evaluation rubric.
    - confidence (float): Confidence in result correctness (placeholder metric).
    """
    passed = False
    score = 0
    confidence = 100
    details = {}

    # material properties
    young = 1
    poisson = 0.3
    ext_stiff = 0.0

    # constraints
    Emin = 1e-9
    volfrac = 1.1
    move = 0.25

    # mesh dimensions
    nelx = 100
    # nely = 100
    crack_length = 50

    # optimization parameters
    penal = 1
    rmin = 1.5
    filt = 'density'
    loopy = 50  # math.inf
    delta = 0.001

    # plotting and printing options
    verbose = True
    history = False


    # loading case object, other classes can be selected and created
    load = CompactTension(nelx, crack_length, young, Emin, poisson, ext_stiff)

    # constraints object created
    den_con = DensityConstraint(load, move, volume_frac=volfrac, density_min=1, density_max=2)

    # FEA object is generated, other solvers can be selected and created
    fesolver = CvxFEA(verbose=verbose)

    # create optimizer object and initialise the problem
    optimizer = Topopt(den_con, load, fesolver, verbose=verbose, history=history)

    # compute
    y, x_history, K_y = optimizer.layout(penal, rmin, delta, loopy, filt)

    try:
        y_hat = np.array(llm_response.config.y_hat)
        K_y_hat = llm_response.config.K_y_hat

        # job completed
        score += 10
        # stress intensity factor Error
        KE = abs((K_y_hat - K_y) / K_y)
        sh = y_hat.shape
        if sh[1] == nelx and sh[0] == int(np.round(nelx/1.25*1.2/2)):
            score += 20
            details['y_hat_shape'] = "Pass"
        else:
            details['y_hat_shape'] = "Fail"
        if KE < 0.05:
            score += 70
            details['stress_error'] = f"Pass (KE={KE:.4f})"
        else:
            details['stress_error'] = f"Fail (KE={KE:.4f})"

        # Determine pass/fail
        passed = score >= 80  # Example threshold

    except Exception as e:
        details['error'] = str(e)
        confidence = 0
        return False, details, 0, confidence

    return passed, details, score, confidence