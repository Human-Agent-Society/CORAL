import numpy as np
# import matlab.engine
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from typing import Tuple, Dict

# importing external modules
import time
import math

# importing custom modules
from loads import HalfBeam, Beam, Canti, Michell, BiAxial
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
    # constraints
    Emin = 1e-9
    volfrac = 0.4
    move = 1
    # mesh dimensions
    nelx = 10
    nely = 10
    # optimizer parameters
    penal = 3.0
    rmin = 3
    filt = 'sensitivity'
    loopy = 100  # math.inf
    delta = 0.005

    # plotting and printing options
    verbose = True
    plotting = True
    save_plot = True
    history = False

    # constraints object created
    den_con = DensityConstraint(nelx, nely, move, volume_frac=volfrac)

    # loading case object, other classes can be selected and created
    load = Canti(nelx, nely, young, Emin, poisson)

    # FEA object is generated, other solvers can be selected and created
    fesolver = CvxFEA(verbose=verbose)

    # create optimizer object and initialise the problem
    optimizer = Topopt(den_con, load, fesolver, verbose=verbose)

    # execute the optimization
    t = time.time()
    x, x_history, C_y = optimizer.layout(penal, rmin, delta, loopy, filt, history)
    print('Elapsed time is: ', time.time() - t, 'seconds.')

    try:
        y_hat = np.array(llm_response.config.y_hat)
        C_y_hat = llm_response.config.C_y_hat
        # VF_y_hat = llm_response.config.VF_y_hat
        # load_y_hat = np.array(llm_response.config.load_y_hat)
        # floating_material_y_hat = llm_response.config.floating_material_y_hat

        # Check shape and binary content of y_hat
        # if y_hat.shape == (64, 64) and np.isin(y_hat, [0, 1]).all():
        #     score += 40
        #     details['y_hat_shape_and_values'] = "Pass"
        # else:
        #     details['y_hat_shape_and_values'] = "Fail"
        # job completed
        score += 10
        # Compliance Error
        CE = abs((C_y_hat - C_y) / C_y)
        sh = y_hat.shape
        if sh[0] == nelx and sh[1] == nely:
            score += 20
            details['y_hat_shape'] = "Pass"
        else:
            details['y_hat_shape'] = "Fail"
        if CE < 0.05:
            score += 70
            details['compliance_error'] = f"Pass (CE={CE:.4f})"
        else:
            details['compliance_error'] = f"Fail (CE={CE:.4f})"

        # Determine pass/fail
        passed = score >= 80  # Example threshold

    except Exception as e:
        details['error'] = str(e)
        confidence = 0
        return False, details, 0, confidence

    return passed, details, score, confidence