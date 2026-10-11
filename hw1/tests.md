# Отчёт о тестах HW1

expected/actual — имя первого токена (включая WS/COMMENT) или None.

| input | expected | actual | ok | note |
| --- | --- | --- | --- | --- |
| `''` | None | None | PASS | пустая строка |
| `' \t\r\n'` | WS | WS | PASS | только пробелы (skip) |
| `'  '` | WS | WS | PASS | несколько пробелов (skip) |
| `'// comment'` | COMMENT | COMMENT | PASS | комментарий (skip) |
| `'//'` | COMMENT | COMMENT | PASS | пустой комментарий (skip) |
| `'00'` | INT | INT | PASS | Отрицательный: INT(0) + INT(0), не один INT |
| `'01'` | INT | INT | PASS | Отрицательный: INT(0) + INT(1), не один INT |
| `'functio'` | IDENT | IDENT | PASS | Отрицательный: префикс keyword -> IDENT |
| `'iff'` | IDENT | IDENT | PASS | Отрицательный: не keyword -> IDENT |
| `'==='` | OP | OP | PASS | maximal munch: OP(==) + OP(=) |
| `'/ /'` | OP | OP | PASS | Отрицательный: деление, не COMMENT |
| `'1π'` | INT | INT | PASS | Отрицательный: 1 корректно, затем non-ASCII |
| `'123abc'` | INT | INT | PASS | Отрицательный: не IDENT: начинается с цифры |
| `'0'` | INT | INT | PASS | целое число |
| `'7'` | INT | INT | PASS | целое число |
| `'42'` | INT | INT | PASS | целое число |
| `'100'` | INT | INT | PASS | целое число |
| `'foo'` | IDENT | IDENT | PASS | идентификатор |
| `'_x'` | IDENT | IDENT | PASS | идентификатор |
| `'foo_bar'` | IDENT | IDENT | PASS | идентификатор |
| `'_1'` | IDENT | IDENT | PASS | идентификатор |
| `'function'` | FUNCTION | FUNCTION | PASS | ключевое слово |
| `'function;'` | FUNCTION | FUNCTION | PASS | ключевое слово перед разделителем |
| `'functionx'` | IDENT | IDENT | PASS | Отрицательный: более длинный IDENT, не keyword |
| `'returns'` | RETURNS | RETURNS | PASS | ключевое слово |
| `'returns;'` | RETURNS | RETURNS | PASS | ключевое слово перед разделителем |
| `'returnsx'` | IDENT | IDENT | PASS | Отрицательный: более длинный IDENT, не keyword |
| `'uses'` | USES | USES | PASS | ключевое слово |
| `'uses;'` | USES | USES | PASS | ключевое слово перед разделителем |
| `'usesx'` | IDENT | IDENT | PASS | Отрицательный: более длинный IDENT, не keyword |
| `'while'` | WHILE | WHILE | PASS | ключевое слово |
| `'while;'` | WHILE | WHILE | PASS | ключевое слово перед разделителем |
| `'whilex'` | IDENT | IDENT | PASS | Отрицательный: более длинный IDENT, не keyword |
| `'if'` | IF | IF | PASS | ключевое слово |
| `'if;'` | IF | IF | PASS | ключевое слово перед разделителем |
| `'ifx'` | IDENT | IDENT | PASS | Отрицательный: более длинный IDENT, не keyword |
| `'else'` | ELSE | ELSE | PASS | ключевое слово |
| `'else;'` | ELSE | ELSE | PASS | ключевое слово перед разделителем |
| `'elsex'` | IDENT | IDENT | PASS | Отрицательный: более длинный IDENT, не keyword |
| `'assert'` | ASSERT | ASSERT | PASS | ключевое слово |
| `'assert;'` | ASSERT | ASSERT | PASS | ключевое слово перед разделителем |
| `'assertx'` | IDENT | IDENT | PASS | Отрицательный: более длинный IDENT, не keyword |
| `'assume'` | ASSUME | ASSUME | PASS | ключевое слово |
| `'assume;'` | ASSUME | ASSUME | PASS | ключевое слово перед разделителем |
| `'assumex'` | IDENT | IDENT | PASS | Отрицательный: более длинный IDENT, не keyword |
| `'invariant'` | INVARIANT | INVARIANT | PASS | ключевое слово |
| `'invariant;'` | INVARIANT | INVARIANT | PASS | ключевое слово перед разделителем |
| `'invariantx'` | IDENT | IDENT | PASS | Отрицательный: более длинный IDENT, не keyword |
| `'length'` | LENGTH | LENGTH | PASS | ключевое слово |
| `'length;'` | LENGTH | LENGTH | PASS | ключевое слово перед разделителем |
| `'lengthx'` | IDENT | IDENT | PASS | Отрицательный: более длинный IDENT, не keyword |
| `'true'` | TRUE | TRUE | PASS | ключевое слово |
| `'true;'` | TRUE | TRUE | PASS | ключевое слово перед разделителем |
| `'truex'` | IDENT | IDENT | PASS | Отрицательный: более длинный IDENT, не keyword |
| `'false'` | FALSE | FALSE | PASS | ключевое слово |
| `'false;'` | FALSE | FALSE | PASS | ключевое слово перед разделителем |
| `'falsex'` | IDENT | IDENT | PASS | Отрицательный: более длинный IDENT, не keyword |
| `'not'` | NOT | NOT | PASS | ключевое слово |
| `'not;'` | NOT | NOT | PASS | ключевое слово перед разделителем |
| `'notx'` | IDENT | IDENT | PASS | Отрицательный: более длинный IDENT, не keyword |
| `'and'` | AND | AND | PASS | ключевое слово |
| `'and;'` | AND | AND | PASS | ключевое слово перед разделителем |
| `'andx'` | IDENT | IDENT | PASS | Отрицательный: более длинный IDENT, не keyword |
| `'or'` | OR | OR | PASS | ключевое слово |
| `'or;'` | OR | OR | PASS | ключевое слово перед разделителем |
| `'orx'` | IDENT | IDENT | PASS | Отрицательный: более длинный IDENT, не keyword |
| `'=='` | OP | OP | PASS | оператор из спецификации |
| `'!='` | OP | OP | PASS | оператор из спецификации |
| `'<='` | OP | OP | PASS | оператор из спецификации |
| `'>='` | OP | OP | PASS | оператор из спецификации |
| `'<'` | OP | OP | PASS | оператор из спецификации |
| `'>'` | OP | OP | PASS | оператор из спецификации |
| `'='` | OP | OP | PASS | оператор из спецификации |
| `'+'` | OP | OP | PASS | оператор из спецификации |
| `'-'` | OP | OP | PASS | оператор из спецификации |
| `'*'` | OP | OP | PASS | оператор из спецификации |
| `'/'` | OP | OP | PASS | оператор из спецификации |
| `','` | DELIM | DELIM | PASS | разделитель из спецификации |
| `';'` | DELIM | DELIM | PASS | разделитель из спецификации |
| `'('` | DELIM | DELIM | PASS | разделитель из спецификации |
| `')'` | DELIM | DELIM | PASS | разделитель из спецификации |
| `'['` | DELIM | DELIM | PASS | разделитель из спецификации |
| `']'` | DELIM | DELIM | PASS | разделитель из спецификации |
| `'{'` | DELIM | DELIM | PASS | разделитель из спецификации |
| `'}'` | DELIM | DELIM | PASS | разделитель из спецификации |
| `'π'` | None | None | PASS | Отрицательный: не токен -> trap |
| `'@'` | None | None | PASS | Отрицательный: не токен -> trap |
| `'#'` | None | None | PASS | Отрицательный: не токен -> trap |
| `'\x80'` | None | None | PASS | Отрицательный: не токен -> trap |
| `'\x00'` | None | None | PASS | Отрицательный: не токен -> trap |
| `'\x0b'` | None | None | PASS | Отрицательный: не токен -> trap |
| `'!'` | None | None | PASS | Отрицательный: не токен -> trap |
| `'&'` | None | None | PASS | Отрицательный: не токен -> trap |

Строк: 93; отрицательных: 30; ошибок: 0.

Проверены эквивалентность ДКА до/после минимизации на корпусе, полнота таблиц, достижимость состояний и единственная замкнутая непринимающая ловушка.

ALL PASS
