"""
Created on Tue Jul 10 15:59:56 2018
This code is meant to calculate the stiffness matrix of a nth order 2D element
The shape functions and the nodal coordinates need to be setup

@author: bram
"""

import csv
import sympy as sym
from sympy.matrices import zeros
from sympy.integrals.quadrature import gauss_legendre
from IPython.display import display

# setting up printing options
sym.init_printing(use_latex=True)

# setting up the variables
xi, eta = sym.symbols("xi eta")
E, nu = sym.symbols("E nu")

# Coordinates and shape functions Cubic element
x = [-1, -1/3, 1/3, 1, 1, 1, 1, 1/3, -1/3, -1, -1, -1]
y = [-1, -1, -1, -1, -1/3, 1/3, 1, 1, 1, 1, 1/3, -1/3]
N0 = 1/32 * ((1 - xi)*   (1 - eta)*   (-10 + 9*xi**2 + 9*eta**2))
N1 = 9/32 * ((1 - xi**2)*(1 - eta)*   (1 - 3*xi))
N2 = 9/32 * ((1 - xi**2)*(1 - eta)*   (1 + 3*xi))
N3 = 1/32 * ((1 + xi)*   (1 - eta)*   (-10 + 9*xi**2 + 9*eta**2))
N4 = 9/32 * ((1 + xi)*   (1 - eta**2)*(1 - 3*eta))
N5 = 9/32 * ((1 + xi)*   (1 - eta**2)*(1 + 3*eta))
N6 = 1/32 * ((1 + xi)*   (1 + eta)*   (-10 + 9*xi**2 + 9*eta**2))
N7 = 9/32 * ((1 - xi**2)*(1 + eta)*   (1 + 3*xi))
N8 = 9/32 * ((1 - xi**2)*(1 + eta)*   (1 - 3*xi))
N9 = 1/32 * ((1 - xi)*   (1 + eta)*   (-10 + 9*xi**2 + 9*eta**2))
N10 = 9/32 * ((1 - xi)*  (1 - eta**2)*(1 + 3*eta))
N11 = 9/32 * ((1 - xi)*  (1 - eta**2)*(1 - 3*eta))
N = [N0, N1, N2, N3, N4, N5, N6, N7, N8, N9, N10, N11]

# Coordinates an shape funcitons of Quadratic elements
#x = [-1, 0, 1, 1, 1, 0, -1, -1]
#y = [-1, -1, -1, 0, 1, 1, 1, 0]
#N0 = 1/4 * ((1 - xi)*   (1 - eta)*(-1 - xi - eta))
#N1 = 1/2 * ((1 - xi**2)*(1 - eta))
#N2 = 1/4 * ((1 + xi)*   (1 - eta)*(-1 + xi - eta))
#N3 = 1/2 * ((1 + xi)*   (1 - eta**2))
#N4 = 1/4 * ((1 + xi)*   (1 + eta)*(-1 + xi + eta))
#N5 = 1/2 * ((1 - xi**2)*(1 + eta))
#N6 = 1/4 * ((1 - xi)*   (1 + eta)*(-1 - xi + eta))
#N7 = 1/2 * ((1 - xi)*   (1 - eta**2))
#N = [N0, N1, N2, N3, N4, N5, N6, N7]

# Shapefuncions and coordinates linear elment
#x = [-0, 1, 1, -0]
#y = [-0, -0, 1, 1]
#N0 = 1/4*((1 - xi)*(1 - eta))
#N1 = 1/4*((1 + xi)*(1 - eta))
#N2 = 1/4*((1 + xi)*(1 + eta))
#N3 = 1/4*((1 - xi)*(1 + eta))
#N = [N0, N1, N2, N3]


"""
This part of the code does calculate the jacobean. at first in will express
X and Y funcions in terms of the shape functions and the node locations.

Then it directly calculates the Jacobian with symbolic manipulation.
The Jacobian is also simplified and inverted for later calculations
"""
X = 0
Y = 0
for i in range(len(N)):
    X += N[i]*x[i]
    Y += N[i]*y[i]

XiEtaCoord = sym.Matrix([xi, eta])  # Coordinate system
XYCoord = sym.Matrix([X, Y])
J = sym.simplify(XYCoord.jacobian(XiEtaCoord))

invJ = sym.simplify(J**-1)
detJ = sym.simplify(J.det())

"""
Here the B matrix is calculated, the method is based upon the equation 8.17
from the "Finite Element Method in Engineering Science" from Zienkiewicz where
⎡dNi/dx⎤            ⎡dNi/dξ⎤
⎣dNi/dy⎦ = inv([J]) ⎣dNi/dη⎦

and:
    
      ⎡dNi/dx   0     ⎤
Bi =  ⎢0        dNi/dy⎥
      ⎣dNi/dy   dNi/dx⎦
"""
B = zeros(3, 2*len(N))

for i in range(len(N)):
    Ni = N[i]
    dNidxi = sym.diff(Ni, xi)
    dNideta = sym.diff(Ni, eta)

    dNidi = sym.Matrix([[dNidxi], [dNideta]])
    dNidI = invJ*dNidi  # Exequte equation 8.17 Zienkiewicz
    B[0:3, 2*i:2*i+2] = sym.Matrix([[dNidI[0], 0], [0, dNidI[1]], [dNidI[1], dNidI[0]]])


"""
Here the material stiffness matrix is defined. Currently the plane stress state
is implemented
"""
D = sym.Matrix([[1, nu, 0], [nu, 1, 0], [0, 0, (1-nu)/2]]) * E/(1-nu**2)


"""
Now the final steps are taken. First B^T * D * B * detJ is calculated.
1  1         
⌠  ⌠         
⎮  ⎮  BDBdetJ dξ dη
⌡  ⌡         
-1 -1
Then the integration is done term by term in the resulting matrix. This is done
so that the printing becomes more clear, every element is printed seperatly.
The integration is now done with a gausian quadrature method as adviced by:
"Basic Finite Element Method as Applied to Injury Biomechanics" from K. Yang
"""
BDBdetJ = B.T * D * B * detJ

k = []

for i in range(2*len(N)):
    ki = []
    for j in range(2*len(N)):
        print("(", i ,", ", j, ")")
        BDBij = BDBdetJ[i, j]
        Kij = sym.integrate(sym.integrate(BDBij, (xi, -1, 1)), (eta, -1, 1))
        ki.append(str(Kij.simplify()))
    k.append(ki)

#f = open("Stiffness_Cubic_PlaneStress.csv", "w+")
#writer = csv.writer(f)
#writer.writerows(k)
#f.close()
