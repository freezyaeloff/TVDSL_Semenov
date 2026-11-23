# HW4. Результаты тестов

Команда из папки `hw4`

```bash
python3 test_ir.py -v
```

Тесты сравнивают результаты выполнения IR до и после оптимизаций, проверяют графы, раскраску, метрики и работу CLI. Текстовый вывод трёх примеров сравнивается с файлами `*.expected.txt`.

| Тест | Что проверяет | Результат |
| --- | --- | --- |
| `CLITests.test_dot_export` | Создание файлов DOT, обратное ребро цикла и исчезновение конфликта после оптимизации. | PASS |
| `CLITests.test_each_cli_switch` | Отдельное отключение каждой оптимизации флагом CLI. | PASS |
| `CLITests.test_frontend_error` | Сообщение об ошибке типов и код выхода 1. | PASS |
| `CLITests.test_missing_file` | Код выхода 2 при отсутствии входного файла. | PASS |
| `CLITests.test_stdin_json_out_and_no_opt` | Чтение из stdin, запись JSON и совпадение обеих версий IR с `--no-opt`. | PASS |
| `IRTests.test_arithmetic_example` | Результаты `calc` на трёх входах и сокращение IR с 9 до 5 инструкций. | PASS |
| `IRTests.test_array_update_value` | Обновление элемента массива с сохранением прежнего значения массива. | PASS |
| `IRTests.test_cfg_and_loop_liveness` | Рёбра CFG цикла, команды в конце блоков и живые переменные на обратном ребре. | PASS |
| `IRTests.test_colored_execution_across_blocks` | Совпадение результатов при замене временных слотами по цветам. | PASS |
| `IRTests.test_conflict_graph_and_reuse` | Рёбра графа конфликтов и повторное использование слотов. | PASS |
| `IRTests.test_constant_branch` | Удаление недостижимой ветки и сокращение CFG с 4 до 3 блоков. | PASS |
| `IRTests.test_constant_false_loop` | Удаление тела цикла с условием `false`. | PASS |
| `IRTests.test_contract_failure_point` | Ошибки при нарушении предусловия, постусловия, инварианта и `assume`. | PASS |
| `IRTests.test_dead_division_result_needs_own_slot` | Разные слоты для результата деления и значения, живого в этот момент. | PASS |
| `IRTests.test_errors_survive_dce` | Сохранение ошибок деления, индексации и вызова после удаления мёртвого кода. | PASS |
| `IRTests.test_example_output` | Совпадение вывода трёх примеров с файлами `*.expected.txt`. | PASS |
| `IRTests.test_hw3_arrays_and_contracts` | Исполнение примера HW3 с массивами и контрактами. | PASS |
| `IRTests.test_hw3_ast_file` | Генерация IR и сохранение типов при чтении аннотированного AST из HW3. | PASS |
| `IRTests.test_hw3_branches_and_forward_calls` | Ветвление, вызов функции до её объявления и пустой результат. | PASS |
| `IRTests.test_join_and_reassignment` | Значение переменной после слияния веток и последующих присваиваний. | PASS |
| `IRTests.test_loop_and_call` | Результаты `sum` при пропуске цикла и при вызовах `twice`. | PASS |
| `IRTests.test_named_results_and_shadowing` | Возврат двух именованных результатов и затенение переменной. | PASS |
| `IRTests.test_recursive_call` | Вычисление факториала через рекурсивный вызов. | PASS |
| `IRTests.test_rejects_incorrect_ast` | Отклонение AST с ошибками или неподдерживаемой версией. | PASS |
| `IRTests.test_short_circuit` | Короткое вычисление `and` и `or` без деления на ноль. | PASS |
| `IRTests.test_signed_int` | Округление деления к нулю и переполнение знакового 32-битного числа. | PASS |
| `IRTests.test_switches` | Действие каждого прохода по отдельности и сохранение исходного IR. | PASS |

Все 27 тестов прошли на Python 3.12.0.
