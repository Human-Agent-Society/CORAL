# EVOLVE-BLOCK-START
import pandas as pd
from solver import Algorithm
from typing import Tuple, List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from collections import Counter
import networkx as nx


class Evolved(Algorithm):
    """
    GGR algorithm
    """

    def __init__(self, df: pd.DataFrame = None):
        self.df = df

        self.dep_graph = None  # NOTE: not used, for one way dependency

        self.num_rows = 0
        self.num_cols = 0
        self.column_stats = None
        self.val_len = None
        self.row_stop = None
        self.col_stop = None
        self.base = 2000

    def find_max_group_value(self, df: pd.DataFrame, value_counts: Dict, early_stop: int = 0) -> str:
        # NOTE: recalculate value counts and length for each value
        value_counts = Counter(df.stack())
        weighted_counts = {val: self.val_len[val] * (count - 1) for val, count in value_counts.items()}  # if count > 1
        if not weighted_counts:
            return None
        max_group_val, max_weighted_count = max(weighted_counts.items(), key=lambda x: x[1])
        if max_weighted_count < early_stop:
            return None
        return max_group_val

    def reorder_columns_for_value(self, row, value, column_names, grouped_rows_len: int = 1):
        # cols_with_value will now use attribute access instead of indexing with row[]
        cols_with_value = []
        for idx, col in enumerate(column_names):
            if hasattr(row, col) and getattr(row, col) == value:
                cols_with_value.append(col)
            elif hasattr(row, col.replace(" ", "_")) and getattr(row, col.replace(" ", "_")) == value:
                cols_with_value.append(col)
            else:
                attr_name = f"_{idx}"
                if hasattr(row, attr_name) and getattr(row, attr_name) == value:
                    cols_with_value.append(attr_name)

        if self.dep_graph is not None and grouped_rows_len > 1:
            # NOTE: experimental
            reordered_cols = []
            for col in cols_with_value:
                dependent_cols = self.get_dependent_columns(col)

                # check if dependent columns are in row, and if column exists in row attributes
                valid_dependent_cols = []
                for idx, dep_col in enumerate(dependent_cols):
                    if hasattr(row, dep_col):
                        valid_dependent_cols.append(dep_col)
                    elif hasattr(row, dep_col.replace(" ", "_")):
                        valid_dependent_cols.append(dep_col)
                    else:
                        attr_name = f"_{idx}"
                        if hasattr(row, attr_name):
                            valid_dependent_cols.append(dep_col)

                reordered_cols.extend([col] + valid_dependent_cols)
            cols_without_value = [col for col in column_names if col not in reordered_cols]
            reordered_cols.extend(cols_without_value)
            assert len(reordered_cols) == len(
                column_names
            ), f"Reordered cols len: {len(reordered_cols)}  Original cols len: {len(column_names)}"
            return [getattr(row, col) for col in reordered_cols], cols_with_value
        else:
            cols_without_value = []
            for idx, col in enumerate(column_names):
                if hasattr(row, col) and getattr(row, col) != value:
                    cols_without_value.append(col)
                elif hasattr(row, col.replace(" ", "_")) and getattr(row, col.replace(" ", "_")) != value:
                    cols_without_value.append(col)
                else:
                    # Handle some edge cases
                    attr_name = f"_{idx}"
                    if hasattr(row, attr_name) and getattr(row, attr_name) != value:
                        cols_without_value.append(attr_name)

            reordered_cols = cols_with_value + cols_without_value
            assert len(reordered_cols) == len(
                column_names
            ), f"Reordered cols len: {len(reordered_cols)}  Original cols len: {len(column_names)}"
            return [getattr(row, col) for col in reordered_cols], cols_with_value

    def get_dependent_columns(self, col: str) -> List[str]:
        if self.dep_graph is None or not self.dep_graph.has_node(col):
            return []
        return list(nx.descendants(self.dep_graph, col))

    @lru_cache(maxsize=None)
    def get_cached_dependent_columns(self, col: str) -> List[str]:
        return self.get_dependent_columns(col)

    def fixed_reorder(self, df: pd.DataFrame, row_sort: bool = True) -> Tuple[pd.DataFrame, List[List[str]]]:
        num_rows, column_stats = self.calculate_col_stats(df, enable_index=True)
        reordered_columns = [col for col, _, _, _ in column_stats]
        reordered_df = df[reordered_columns]

        assert reordered_df.shape == df.shape
        column_orderings = [reordered_columns] * num_rows

        if row_sort:
            reordered_df = reordered_df.sort_values(by=reordered_columns, axis=0)

        return reordered_df, column_orderings

    def column_recursion(self, result_df, max_value, grouped_rows, row_stop, col_stop, early_stop):
        cols_settled = []
        with ThreadPoolExecutor() as executor:
            futures = [
                executor.submit(self.reorder_columns_for_value, row, max_value, grouped_rows.columns.tolist(), len(grouped_rows))
                for row in grouped_rows.itertuples(index=False)
            ]
            for i, future in enumerate(as_completed(futures)):
                reordered_row, cols_settled = future.result()
                result_df.loc[i] = reordered_row

        grouped_value_counts = Counter()

        if not result_df.empty:
            # Group by the first column
            grouped_result_df = result_df.groupby(result_df.columns[0])
            grouped_value_counts = Counter(grouped_rows.stack())  # this is still faster than updating from cached value counts

            for _, group in grouped_result_df:
                if group[group.columns[0]].iloc[0] != max_value:
                    continue

                dependent_cols = self.get_cached_dependent_columns(group.columns[0])
                length_of_settle_cols = len(cols_settled)

                if dependent_cols:
                    assert length_of_settle_cols >= 1, f"Dependent columns should be no less than 1, but got {length_of_settle_cols}"

                    # test the first length_of_settle_cols columns, each column has nunique == 1
                    for col in group.columns[:length_of_settle_cols]:
                        assert group[col].nunique() == 1, f"Column {col} should have nunique == 1, but got {group[col].nunique()}"

                    # drop all the settled columns and reorder the rest
                    group_remainder = group.iloc[:, length_of_settle_cols:]
                else:
                    group_remainder = group.iloc[:, 1:]

                grouped_remainder_value_counts = Counter(group_remainder.stack())

                reordered_group_remainder, _ = self.recursive_reorder(
                    group_remainder, grouped_remainder_value_counts, early_stop=early_stop, row_stop=row_stop, col_stop=col_stop + 1
                )
                # Update the group with the reordered columns
                if dependent_cols:
                    group.iloc[:, length_of_settle_cols:] = reordered_group_remainder.values
                else:
                    group.iloc[:, 1:] = reordered_group_remainder.values

                result_df.update(group)
                break

        return result_df, grouped_value_counts

    def recursive_reorder(
        self,
        df: pd.DataFrame,
        value_counts: Dict,
        early_stop: int = 0,
        original_columns: List[str] = None,
        row_stop: int = 0,
        col_stop: int = 0,
    ) -> Tuple[pd.DataFrame, List[List[str]]]:
        if df.empty or len(df.columns) == 0 or len(df) == 0:
            return df, []

        if self.row_stop is not None and row_stop >= self.row_stop:
            return self.fixed_reorder(df)

        if self.col_stop is not None and col_stop >= self.col_stop:
            return self.fixed_reorder(df)

        if original_columns is None:
            original_columns = df.columns.tolist()

        # Find the max group value using updated counts
        max_value = self.find_max_group_value(df, value_counts, early_stop=early_stop)
        if max_value is None:
            # If there is no max value, then fall back to fixed reorder
            return self.fixed_reorder(df)

        grouped_rows = df[df.isin([max_value]).any(axis=1)]
        remaining_rows = df[~df.isin([max_value]).any(axis=1)]

        # If there is no grouped rows, return the original DataFrame
        if grouped_rows.empty:
            return self.fixed_reorder(df)

        result_df = pd.DataFrame(columns=df.columns)

        reordered_remaining_rows = pd.DataFrame(columns=df.columns)  # Initialize empty dataframe first

        # Column Recursion
        result_df, grouped_value_counts = self.column_recursion(result_df, max_value, grouped_rows, row_stop, col_stop, early_stop)

        remaining_value_counts = value_counts - grouped_value_counts  # Approach 1 - update remaining value counts with subtraction

        # Row Recursion
        reordered_remaining_rows, _ = self.recursive_reorder(
            remaining_rows, remaining_value_counts, early_stop=early_stop, row_stop=row_stop + 1, col_stop=col_stop
        )
        old_column_names = result_df.columns.tolist()
        result_cols_reset = result_df.reset_index(drop=True)
        result_rows_reset = reordered_remaining_rows.reset_index(drop=True)
        final_result_df = pd.DataFrame(result_cols_reset.values.tolist() + result_rows_reset.values.tolist())

        if row_stop == 0 and col_stop == 0:
            final_result_df.columns = old_column_names
            final_result_df.columns = final_result_df.columns.tolist()[:-1] + ["original_index"]

        return final_result_df, []

    def recursive_split_and_reorder(self, df: pd.DataFrame, original_columns: List[str] = None, early_stop: int = 0):
        """
        Recursively split the DataFrame into halves until the size is <= 1000, then apply the recursive reorder function.
        """
        if len(df) <= self.base:
            initial_value_counts = Counter(df.stack())
            return self.recursive_reorder(df, initial_value_counts, early_stop, original_columns, row_stop=0, col_stop=0)[0]

        mid_index = len(df) // 2
        df_top_half = df.iloc[:mid_index]
        df_bottom_half = df.iloc[mid_index:]

        with ThreadPoolExecutor() as executor:
            future_top = executor.submit(self.recursive_split_and_reorder, df_top_half, original_columns, early_stop)
            future_bottom = executor.submit(self.recursive_split_and_reorder, df_bottom_half, original_columns, early_stop)

        reordered_top_half = future_top.result()
        reordered_bottom_half = future_bottom.result()

        assert reordered_bottom_half.shape == df_bottom_half.shape
        reordered_df = pd.concat([reordered_top_half, reordered_bottom_half], axis=0, ignore_index=True)

        assert reordered_df.shape == df.shape

        return reordered_df

    @lru_cache(maxsize=None)
    def calculate_length(self, value):
        if isinstance(value, bool):
            return 4**2
        if isinstance(value, (int, float)):
            return len(str(value)) ** 2
        if isinstance(value, str):
            return len(value) ** 2
        return 0

    def reorder(
        self,
        df: pd.DataFrame,
        early_stop: int = 0,
        row_stop: int = None,
        col_stop: int = None,
        col_merge: List[List[str]] = [],
        one_way_dep: List[Tuple[str, str]] = [],
        distinct_value_threshold: float = 0.8,
        parallel: bool = True,
    ) -> Tuple[pd.DataFrame, List[List[str]]]:
        # Prepare
        initial_df = df.copy()
        if col_merge:
            self.num_rows, self.column_stats = self.calculate_col_stats(df, enable_index=True)
            reordered_columns = [col for col, _, _, _ in self.column_stats]
            for col_to_merge in col_merge:
                final_col_order = [col for col in reordered_columns if col in col_to_merge]
                df = self.merging_columns(df, final_col_order, prepended=False)
        self.num_rows, self.column_stats = self.calculate_col_stats(df, enable_index=True)
        self.column_stats = {col: (num_groups, avg_len, score) for col, num_groups, avg_len, score in self.column_stats}

        # One way dependency statistics [not used]
        if one_way_dep is not None and len(one_way_dep) > 0:
            self.dep_graph = nx.DiGraph()
            for dep in one_way_dep:
                col1 = [col for col in df.columns if dep[0] in col]
                col2 = [col for col in df.columns if dep[1] in col]
                assert len(col1) == 1, f"Expected one column to match {dep[0]}, but got {len(col1)}"
                assert len(col2) == 1, f"Expected one column to match {dep[1]}, but got {len(col2)}"
                col1 = col1[0]
                col2 = col2[0]
                self.dep_graph.add_edge(col1, col2)

        # Discard too distinct columns by threshold [optional]
        nunique_threshold = len(df) * distinct_value_threshold
        columns_to_discard = [col for col in df.columns if df[col].nunique() > nunique_threshold]
        columns_to_discard = sorted(columns_to_discard, key=lambda x: self.column_stats[x][2], reverse=True)
        columns_to_recurse = [col for col in df.columns if col not in columns_to_discard]
        df["original_index"] = range(len(df))
        discarded_columns_df = df[columns_to_discard + ["original_index"]]
        df_to_recurse = df[columns_to_recurse + ["original_index"]]
        recurse_df = df_to_recurse

        self.column_stats = {col: stats for col, stats in self.column_stats.items() if col not in columns_to_discard}
        initial_value_counts = Counter(recurse_df.stack())
        self.val_len = {val: self.calculate_length(val) for val in initial_value_counts.keys()}

        self.row_stop = row_stop if row_stop else len(recurse_df)
        self.col_stop = col_stop if col_stop else len(recurse_df.columns.tolist())
        print("*" * 80)
        print(f"DF columns = {df.columns}")
        # print(f"Early stop = {early_stop}")
        # print(f"Row recursion stop depth = {self.row_stop}, Column recursion stop depth = {self.col_stop}")
        print("*" * 80)

        # Eary stop and fall back
        recurse_df, _ = self.fixed_reorder(recurse_df)

        # Recursive reordering
        self.num_cols = len(recurse_df.columns)
        if parallel:
            reordered_df = self.recursive_split_and_reorder(recurse_df, original_columns=columns_to_recurse, early_stop=early_stop)
        else:
            reordered_df, _ = self.recursive_reorder(
                recurse_df,
                initial_value_counts,
                early_stop=early_stop,
            )

        assert (
            reordered_df.shape == recurse_df.shape
        ), f"Reordered DataFrame shape {reordered_df.shape} does not match original DataFrame shape {recurse_df.shape}"
        assert recurse_df["original_index"].is_unique, "Passed in recurse index contains duplicates!"
        assert reordered_df["original_index"].is_unique, "Reordered index contains duplicates!"

        if len(columns_to_discard) > 0:
            final_df = pd.merge(reordered_df, discarded_columns_df, on="original_index", how="left")
        else:
            final_df = reordered_df

        final_df = final_df.drop(columns=["original_index"])

        if not col_merge:
            assert (
                final_df.shape == initial_df.shape
            ), f"Final DataFrame shape {final_df.shape} does not match original DataFrame shape {initial_df.shape}"
        else:
            assert (
                final_df.shape[0] == initial_df.shape[0]
            ), f"Final DataFrame shape {final_df.shape} does not match original DataFrame shape {initial_df.shape}"
            assert (
                final_df.shape[1] == recurse_df.shape[1] + len(columns_to_discard) - 1
            ), f"Final DataFrame shape {final_df.shape} does not match original DataFrame shape {recurse_df.shape}"

        # sort by the first column to get the final order
        final_df = final_df.sort_values(by=final_df.columns.to_list(), axis=0)
        return final_df, []

# EVOLVE-BLOCK-END