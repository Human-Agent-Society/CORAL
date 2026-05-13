# Task: Transmission Muon Tomography Detector Placement Optimization

## 1. Physical and Engineering Background
Cosmic ray muons are highly penetrating elementary particles commonly used for non-destructive, three-dimensional internal imaging of large structures such as pyramids, mountains, or nuclear reactors. The core principle is transmission radiography: muons attenuate differently as they pass through materials of varying densities. By measuring the muon flux after penetrating a target object, one can infer its internal density distribution and discover hidden cavities (e.g., hidden chambers).

**Real-world Engineering Challenges**:
1. **Directional Constraints**: Cosmic ray muons originate from the atmosphere, and their flux is highly dependent on the zenith angle ($\theta_z$). The flux is maximum in the vertical downward direction and decreases sharply towards the horizon, following a $\cos^2(\theta_z)$ distribution. Therefore, to capture effective muons penetrating the target, detectors must typically be placed below or to the side of the target object.
2. **Deployment Costs**: High-precision muon detectors are extremely expensive. Furthermore, if they need to be placed underground, exorbitant tunnel excavation costs are incurred. Longer measurement times also lead to higher economic costs.

This task requires the AI Agent to optimize the spatial layout (quantity, position, and orientation) of a detector array under limited budget and topographical constraints, maximizing the effective signal reception rate for a specific Region of Interest (ROI) inside the target.

## 2. Physical Model & Environment Setup
* **Target Object**: A square pyramid (simulating a pyramid) with its base centered at $(0, 0, 0)$ on the $z=0$ plane, base side length of $100$ m, and height of $100$ m (apex at $(0, 0, 100)$).
* **Region of Interest (ROI)**: A suspected hidden chamber is known to exist inside the pyramid, with its center coordinates at $P_{\text{ROI}} = (0, 0, 30)$.
* **Agent Action**: Deploy $N$ detectors. Each detector $i$ is defined by 5 parameters: $d_i = (x_i, y_i, z_i, \theta_i, \phi_i)$.
  * $(x_i, y_i, z_i)$: Center coordinates of the detector (in meters).
  * $(\theta_i, \phi_i)$: The polar and azimuthal angles of the detector panel's normal vector in spherical coordinates (in degrees).

## 3. Objective Function
The goal is to maximize the total score $J(X)$, which balances the **ROI signal significance** and the **total engineering cost**:

$$J(X) = \text{TotalSignal}(X) - \lambda \cdot \text{Cost}(X)$$

### 3.1 Effective Signal (TotalSignal)
The effective muon signal $S_i$ passing through the ROI and received by each detector $i$ is estimated as:
$$S_i = A \cdot \frac{\cos^2(\theta_z)}{D_i^2} \cdot \max(0, \cos(\gamma_i))$$
* $A$: Detector standard area constant (set to $1.0$).
* $D_i$: Distance from the detector to the ROI center.
* $\theta_z$: The angle between the line of sight from the detector to the ROI center and the vertical Z-axis (Zenith Angle). Note that the target must be above the detector to receive valid signals.
* $\gamma_i$: The incident angle between the incoming muon ray (from ROI to detector) and the detector's normal vector.

The total signal uses a logarithmic function to simulate diminishing returns:
$$\text{TotalSignal}(X) = 100 \cdot \ln\left(1 + \sum_{i=1}^{N} S_i\right)$$

### 3.2 Total Engineering Cost (Cost)
$$\text{Cost}(X) = N \cdot C_{\text{base}} + \sum_{i=1}^{N} \text{DiggingCost}(x_i, y_i, z_i)$$
* **Base Cost**: The manufacturing cost of each detector is $C_{\text{base}} = 20.0$.
* **Digging Cost**: If $z_i < 0$ (placed underground), an excavation fee is required: $\text{DiggingCost} = 1.5 \cdot |z_i|$. Furthermore, detectors are strictly prohibited from being placed *inside* the pyramid envelope. A massive penalty is applied for violations.
* **Weight**: $\lambda = 1.0$.

## 4. I/O Specification

### 4.1 Agent's Action
The Agent must output a `solution.json` file containing a maximum of 15 detectors ($N \le 15$). Coordinate bounds should be within $[-200, 200]$ meters.
```json
{
  "detectors": [
    {"x": 80.0, "y": 0.0, "z": -10.0, "theta": 45.0, "phi": 180.0},
    {"x": -50.0, "y": -50.0, "z": 0.0, "theta": 60.0, "phi": 45.0}
  ]
}