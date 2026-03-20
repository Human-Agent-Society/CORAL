from concurrent.futures import ThreadPoolExecutor
import pandas as pd
from typing import List, Tuple

class TrieNode:
    def __init__(self):
        self.children = {}
        self.end_of_word = False


class Trie:
    def __init__(self):
        self.root = TrieNode()

    def insert(self, word):
        node = self.root
        for char in word:
            if char not in node.children:
                node.children[char] = TrieNode()
            node = node.children[char]
        node.end_of_word = True

    def longest_common_prefix(self, word):
        node = self.root
        common_prefix_length = 0
        for char in word:
            if char in node.children:
                common_prefix_length += len(char)
                node = node.children[char]
            else:
                break
        return common_prefix_length

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

def evaluate_df_prefix_hit_cnt(df: pd.DataFrame) -> Tuple[int, int]:
    """
    Function to evaluate the prefix hit count of a DataFrame
    """

    def max_overlap(trie, row_string):
        return min(len(row_string), trie.longest_common_prefix(row_string))


    trie = Trie()
    total_prefix_hit_count = 0
    total_string_length = 0

    def process_row(index, row):
        nonlocal total_string_length
        row_string = "".join(row.fillna("").astype(str).values)  # No spaces between columns
        total_string_length += len(row_string)
        row_prefix_hit_count = max_overlap(trie, row_string)
        trie.insert(row_string)
        return row_prefix_hit_count

    with ThreadPoolExecutor() as executor:
        results = executor.map(process_row, df.index, [row for _, row in df.iterrows()])

    total_prefix_hit_count = sum(results)
    total_prefix_hit_rate = total_prefix_hit_count / total_string_length
    assert total_prefix_hit_count <= total_string_length
    print(f"Total string length: {total_string_length}")
    no_cache_pricing = 2.5 / 5  # per 1M if not cached
    cache_pricing = 1.25 / 5  # per 1M if cached
    cached_tokens_pricing = total_prefix_hit_count * cache_pricing / 1e6
    non_cached_tokens_pricing = (total_string_length - total_prefix_hit_count) * no_cache_pricing / 1e6
    print(
        f"Cached tokens pricing = {round(cached_tokens_pricing,2)}, Non-cached tokens pricing = {round(non_cached_tokens_pricing,2)}, total pricing = {round(cached_tokens_pricing + non_cached_tokens_pricing,2)}"
    )
    return total_prefix_hit_count, total_prefix_hit_rate * 100