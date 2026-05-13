import numpy as np
import cv2
import os
from sklearn.metrics import mean_squared_error

def evaluate_llm_response(llm_response):
    """
    Evaluate the image filtering code returned by the LLM.
    Load the only image in 'images', denoise it using LLM code, save result to 'results' folder,
    and compute MSE and PSNR using a known reference image.
    """
    try:
        # === Step 1: Locate the only image in 'images' ===
        input_folder = 'images'
        image_files = [f for f in os.listdir(input_folder)
                       if f.lower().endswith(('.png', '.jpg', '.jpeg'))]

        if len(image_files) != 1:
            raise ValueError("The 'images' folder must contain exactly one image.")

        image_name = image_files[0]
        image_path = os.path.join(input_folder, image_name)
        noisy_img = cv2.imread(image_path)
        original_img = cv2.imread('original_image.png')

        if noisy_img is None:
            raise IOError(f"Failed to read image: {image_path}")
        if original_img is None:
            raise IOError("Failed to read the reference image: 'original_image.png'")

        # === Step 2: Execute LLM code to perform denoising ===
        function_code = llm_response.config.function_code
        with open("function.txt", "w", encoding="utf-8") as file:
            file.write(function_code)

        exec_globals = {'np': np, 'cv2': cv2, 'img_noisy': noisy_img}

        try:
            exec(function_code, exec_globals)
            if 'denoise_image' not in exec_globals:
                raise ValueError("The LLM response did not define the required 'denoise_image' function.")
            
            filtered_img = exec_globals['denoise_image'](noisy_img)
            if filtered_img is None:
                raise ValueError("The 'denoise_image' function returned None.")
        except Exception as e:
            return False, {"error": "LLM-generated function execution failed", "exception": str(e)}, 0, 0

        # === Step 3: Save result to 'results' folder ===
        os.makedirs('results', exist_ok=True)
        base_name, ext = os.path.splitext(image_name)
        output_path = os.path.join('results', f"{base_name}_filtered{ext}")
        cv2.imwrite(output_path, filtered_img)

        # === Step 4: Compute MSE and PSNR ===
        mse = mean_squared_error(original_img.flatten(), filtered_img.flatten())
        psnr = cv2.PSNR(original_img, filtered_img)

        # === Step 5: Compute final score ===
        MSE_best = 0
        MSE_worst = 500
        PSNR_best = 40
        PSNR_worst = 10

        w_psnr = 0.7
        w_mse = 0.3

        mse_norm = max(0, min(1, (MSE_worst - mse) / (MSE_worst - MSE_best)))
        psnr_norm = max(0, min(1, (psnr - PSNR_worst) / (PSNR_best - PSNR_worst)))
        score = 100 * (w_mse * mse_norm + w_psnr * psnr_norm)

        passed = mse < 200
        metrics = {"mse": mse, "psnr": psnr}

        details = {
            "strategy": llm_response.config.denoising_strategy,
            "score": metrics,
            "denoising function": function_code
        }

        return passed, details, score, 100

    except Exception as e:
        return False, {"error": str(e)}, 0, 0
