import pandas as pd
from typing import List, Tuple
from concurrent.futures import ThreadPoolExecutor
from utils import Trie
import time


class Algorithm:
    def __init__(self, df: pd.DataFrame = None):
        self.df = df

    def reorder(self, df: pd.DataFrame) -> pd.DataFrame:
        raise NotImplementedError("Subclasses should implement this!")

    @staticmethod
    def evaluate_df_prefix_hit_cnt(self, df: pd.DataFrame) -> int:
        """
        Function to evaluate the prefix hit count of a DataFrame
        """

        def max_overlap(trie, row_string):
            return trie.longest_common_prefix(row_string)

        trie = Trie()
        total_prefix_hit_count = 0

        def process_row(index, row):
            row_string = "".join(row.astype(str).values)  # No spaces between columns
            row_prefix_hit_count = max_overlap(trie, row_string)
            trie.insert(row_string)
            return row_prefix_hit_count

        with ThreadPoolExecutor() as executor:
            results = executor.map(process_row, df.index, [row for _, row in df.iterrows()])

        total_prefix_hit_count = sum(results)
        return total_prefix_hit_count

    @staticmethod
    def evaluate_cell_hit_cnt(df: pd.DataFrame) -> int:
        """
        Function to evaluate the prefix hit count of a DataFrame based on exact cell matching.
        For a cell to be a hit, all previous cells in the row must also be hits.
        """

        total_prefix_hit_count = 0
        seen_rows = set()  # Cache of fully processed rows

        def process_row(index, row):
            nonlocal seen_rows
            prefix_hit_count = 0
            current_row_cache = []

            for col_value in row:
                # Check if adding this cell matches exactly with prior cache
                current_row_cache.append(col_value)
                if tuple(current_row_cache) in seen_rows:
                    prefix_hit_count += 1
                else:
                    break  # Stop counting hits if any cell isn't in the cache

            seen_rows.add(tuple(row))  # Add the fully processed row to cache
            return prefix_hit_count

        # Process each row sequentially (row-to-row comparison for hits)
        for _, row in df.iterrows():
            total_prefix_hit_count += process_row(_, row)

        return total_prefix_hit_count

    @staticmethod
    def get_groups_values(df: pd.DataFrame):
        """
        Function to get the value counts of a DataFrame
        """
        if df.empty:
            return {}
        value_counts = df.stack().value_counts()
        if value_counts.empty:
            return {}
        return value_counts

    @staticmethod
    def calculate_length(value):
        val = 0
        if isinstance(value, bool):
            val = 4  # length of 'True' or 'False'
        elif isinstance(value, (int, float)):
            val = len(str(value))
        elif isinstance(value, str):
            val = len(value)
        else:
            val = 0
        return val**2

    @staticmethod
    def drop_col(df: pd.DataFrame, col):
        return df.drop(columns=[col])

    @staticmethod
    def drop_rows(df: pd.DataFrame, rows):
        return df.drop(index=rows)

    @staticmethod
    def merging_columns(df: pd.DataFrame, col_names: List[str], delimiter: str = "_", prepended: bool = False) -> pd.DataFrame:
        if not all(col in df.columns for col in col_names):
            raise ValueError("Column names not found in DataFrame")

        # before merging, check that each column to be merged has the same number of unique values
        if len(set(df[col_names].nunique())) != 1:
            raise ValueError(f"Columns to be merged {col_names}, do not have the same number of unique values: {df.nunique().sort_values()}")

        merged_names = delimiter.join(col_names)
        if prepended:
            df[merged_names] = df[col_names].apply(
                lambda x: merged_names + ": " + delimiter.join([val.split(": ", 1)[1] for col, val in zip(col_names, x)]), axis=1
            )
        else:
            df[merged_names] = df[col_names].apply(lambda x: "".join([f"{val}" for val in x]), axis=1)
        df = df.drop(columns=col_names)
        return df

    @staticmethod
    def calculate_col_stats(df: pd.DataFrame, enable_index=False):
        num_rows = len(df)
        column_stats = []
        for col in df.columns:
            if col == "original_index":
                continue

            num_groups = df[col].nunique()
            if df[col].dtype == "object" or df[col].dtype == "string":
                avg_length = df[col].astype(str).str.len().mean()
            elif df[col].dtype == "bool":
                avg_length = 4  # Assuming 'True' or 'False' as average length
            elif df[col].dtype in ["int64", "float64"]:
                avg_length = df[col].astype(str).str.len().mean()
            else:
                avg_length = 0

            avg_length = avg_length**2

            if num_groups == 0:
                score = 0
            else:
                # Average size per group: number of rows in each group
                avg_size_per_group = num_rows / num_groups
                # score = avg_size_per_group * avg_length
                score = avg_length * (avg_size_per_group - 1)

                if num_rows == num_groups:  # no sharing at all
                    score = 0
            column_stats.append((col, num_groups, avg_length, score))

        # original_index all distinct values, so give lowest score
        if enable_index and "original_index" in df.columns:
            column_stats.append(("original_index", len(df), 0, 0))

        # Sort the columns based on the score
        column_stats.sort(key=lambda x: x[3], reverse=True)
        return num_rows, column_stats
