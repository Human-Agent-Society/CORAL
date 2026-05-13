# References

- `car_surface_points.npy`: reference surface point set (shape `(M, 3)`).
- `extract_car_mesh.py`: helper script to generate `car_surface_points.npy` from the raw dataset.

Generate the reference points after downloading the dataset:

```bash
python extract_car_mesh.py \
  --data-dir ../data/physense_car_data \
  --output car_surface_points.npy
```
