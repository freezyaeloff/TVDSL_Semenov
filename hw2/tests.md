# HW2. Результаты тестов

Команда: `python test_parser.py` или `python funny_parser.py --tests`.

Ожидаемые AST, токены и ошибки проверяются утверждениями в `test_parser.py`.

| Тест | Результат |
| --- | --- |
| `CommandLineTests.test_errors_exit_code_and_partial_ast` | PASS |
| `CommandLineTests.test_json_stdout` | PASS |
| `CommandLineTests.test_output_from_another_directory` | PASS |
| `LexerTests.test_bad_character_position` | PASS |
| `LexerTests.test_maximal_munch` | PASS |
| `LexerTests.test_non_ascii_comment_is_rejected_by_hw1` | PASS |
| `LexerTests.test_positions_and_skipped_tokens` | PASS |
| `LexerTests.test_windows_line_endings` | PASS |
| `NegativeTests.test_empty_input` | PASS |
| `NegativeTests.test_extra_tokens` | PASS |
| `NegativeTests.test_invalid_character` | PASS |
| `NegativeTests.test_many_broken_statements_do_not_loop` | PASS |
| `NegativeTests.test_missing_expression_with_recovery` | PASS |
| `NegativeTests.test_missing_function_brace_recovers_to_next_function` | PASS |
| `NegativeTests.test_two_errors_and_next_function` | PASS |
| `NegativeTests.test_unclosed_block` | PASS |
| `NegativeTests.test_unclosed_bracket` | PASS |
| `NegativeTests.test_unclosed_parenthesis` | PASS |
| `NegativeTests.test_wrong_assignment_operator` | PASS |
| `PositiveTests.test_array_update_desugars` | PASS |
| `PositiveTests.test_assert_assume_call_and_length` | PASS |
| `PositiveTests.test_ast_snapshot` | PASS |
| `PositiveTests.test_boolean_and_unary` | PASS |
| `PositiveTests.test_contracts_and_uses` | PASS |
| `PositiveTests.test_empty_contracts` | PASS |
| `PositiveTests.test_full_example` | PASS |
| `PositiveTests.test_if_else_if` | PASS |
| `PositiveTests.test_multiple_functions_and_comments` | PASS |
| `PositiveTests.test_precedence_and_left_associativity` | PASS |
| `PositiveTests.test_while_and_invariants` | PASS |

Всего: 30. ALL PASS.
