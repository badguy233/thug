#!/usr/bin/env python
#
# AST2.py
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston,
# MA  02111-1307  USA


import six
import logging
import traceback
import esprima
import unittest

log = logging.getLogger("Thug")


class AST(object):
    # Breakpoints
    ASSIGN_BREAKPOINT = 0x00
    LOOP_BREAKPOINT   = 0x01

    # Assignment operators
    OP_ASSIGN         = '='
    OP_ASSIGN_ADD     = '+='
    OP_ASSIGN_SUB     = '-='
    OP_ASSIGN_MUL     = '*='
    OP_ASSIGN_DIV     = '/='
    OP_ASSIGN_MOD     = '%='
    OP_ASSIGN_SHL     = '<<='
    OP_ASSIGN_SAR     = '>>='
    OP_ASSIGN_SHR     = '>>>='
    OP_ASSIGN_BIT_OR  = '|='
    OP_ASSIGN_BIT_XOR = '^='
    OP_ASSIGN_BIT_AND = '&='

    ASSIGN_OPERATORS = (OP_ASSIGN,
                        OP_ASSIGN_ADD,
                        OP_ASSIGN_SUB,
                        OP_ASSIGN_MUL,
                        OP_ASSIGN_DIV,
                        OP_ASSIGN_MOD,
                        OP_ASSIGN_SHL,
                        OP_ASSIGN_SAR,
                        OP_ASSIGN_SHR,
                        OP_ASSIGN_BIT_OR,
                        OP_ASSIGN_BIT_XOR,
                        OP_ASSIGN_BIT_AND,
                        )

    def __init__(self, script, window = None):
        self.names       = list()
        self.assignments = list()
        self.breakpoints = list()
        self.calls       = set()
        self.shellcodes  = set()
        self.window      = window

        try:
            self.__init_ast(script)
        except:
            log.warning("[AST] Script parsing error (see trace below)")
            log.warning(traceback.format_exc())
            return

        self.walk()

    def __init_ast(self, script):
        self.ast = esprima.parse(script, {'loc'      : True,
                                          'tolerant' : True,
                                          'comments' : True
                                          })

        self.ast = esprima.toDict(self.ast)

    def walk(self, body = None, scope = None):
        if body is None:
            body = self.ast['body']

        for item in body:
            self._walk(item, scope)

    def _walk(self, item, scope):
        # print("[WALK] {}".format(item['type']))
        handler = getattr(self, "on{}".format(item['type']), None)
        if handler:
            handler(item, scope)

    def set_breakpoint(self, stmt, scope, _type):
        bp = {
            'type'  : _type,
            'line'  : stmt['loc']['end']['line'],
            'scope' : scope,
        }

        if bp not in self.breakpoints:
            self.breakpoints.append(bp)

    def onExpressionStatement(self, stmt, scope = None):
        if 'expression' not in stmt:
            return

        if 'type' not in stmt['expression']:
            return

        handler = getattr(self, 'handle{}'.format(stmt['expression']['type']), None)
        if handler:
            handler(stmt, scope)

    def handleAssignmentExpression(self, stmt, scope):
        if 'expression' not in stmt:
            return

        if 'operator' not in stmt['expression']:
            return

        if stmt['expression']['operator'] not in self.ASSIGN_OPERATORS:
            return

        if 'name' in stmt['expression']['left']:
            name = {
                'name'  : stmt['expression']['left']['name'],
                'scope' : scope
            }

            if name not in self.names:
                self.names.append(name)

        self._walk(stmt['expression']['left'], scope)
        self._walk(stmt['expression']['right'], scope)
        self.set_breakpoint(stmt, scope, self.ASSIGN_BREAKPOINT)

    def handleCallExpression(self, stmt, scope):
        if 'expression' not in stmt:
            return

        if 'arguments' not in stmt['expression']:
            return

        for p in stmt['expression']['arguments']:
            if 'type' not in p:
                continue

            if p['type'] in ('Literal', ):
                self.onLiteral(p, scope)

    def onVariableDeclaration(self, item, scope = None):
        if 'declarations' not in item:
            return

        for decl in item['declarations']:
            if 'type' not in decl:
                continue

            if decl['type'] not in ('VariableDeclarator', ):
                continue

            name = {
                'name'  : decl['id']['name'],
                'scope' : scope,
            }

            if name not in self.names:
                self.names.append(name)

            if 'init' in decl:
                self.set_breakpoint(decl, scope, self.ASSIGN_BREAKPOINT)

                if 'raw' in decl['init']:
                    name['value'] = decl['init']['raw']
                    if name not in self.assignments:
                        self.assignments.append(name)

    def onFunctionDeclaration(self, decl, scope = 'global'):
        if 'id' not in decl:
            return

        if 'name' not in decl['id']:
            return

        func_name = decl['id']['name']

        # func_params = [param.name for param in decl['params']]

        if 'body' not in decl:
            return

        if 'body' not in decl['body']:
            return

        self.walk(decl['body']['body'], scope = func_name)

    def onIfStatement(self, stmt, scope):
        if 'alternate' in stmt:
            body = stmt['alternate'].get('body', None)
            if body:
                self.walk(body, scope)

        if 'consequent' in stmt:
            body = stmt['consequent'].get('body', None)
            if body:
                self.walk(body, scope)

    def onForStatement(self, stmt, scope):
        self.set_breakpoint(stmt, scope, self.LOOP_BREAKPOINT)

    def onWhileStatement(self, stmt, scope):
        self.set_breakpoint(stmt, scope, self.LOOP_BREAKPOINT)

    def onDoWhileStatement(self, stmt, scope):
        self.set_breakpoint(stmt, scope, self.LOOP_BREAKPOINT)

    def onForInStatement(self, stmt, scope):
        self.set_breakpoint(stmt, scope, self.LOOP_BREAKPOINT)

    def add_shellcode(self, sc):
        if not isinstance(sc, (six.string_types, six.text_type, six.binary_type)):
            return

        if len(sc) < 32:
            return

        try:
            log.ThugLogging.shellcodes.add(sc.encode('latin1'))
        except:
            self.shellcodes.add(sc)

    def onLiteral(self, litr, scope = None):
        if not litr:
            return

        value = litr.get('value', None)
        if value:
            self.add_shellcode(value)

    def onReturnStatement(self, stmt, scope):
        if not stmt:
            return

        if 'argument' not in stmt:
            return

        value = stmt['argument'].get('value', None)
        if value:
            self.add_shellcode(value)


class TestAST(unittest.TestCase):
    DEBUG = False

    def debug_info(self, script, ast):
        if not self.DEBUG:
            return

        print(script)
        print(ast.names)
        print(ast.breakpoints)

    def testAssign(self):
        script  = """;
            var number = 0;
            number += 1;
            number -= 1;
            number *= 2;
            number /= 3;
        """

        ast = AST(script)
        ast.walk()

        self.debug_info(script, ast)

        for bp in ast.breakpoints:
            bp_type = bp['type']
            bp_line = bp['line']

            if bp_type in (ast.ASSIGN_BREAKPOINT, ):
                assert bp_line in (2, 3, 4, 5, 6, )

    def testVariableDeclaration(self):
        script  = """
            var uninitialized;
            var foo = "bar";
            var number = 1;
        """

        ast = AST(script)
        ast.walk()

        self.debug_info(script, ast)

        names = [p['name'] for p in ast.names]

        assert 'uninitialized' in names
        assert 'foo' in names
        assert 'number' in names

        for bp in ast.breakpoints:
            bp_type = bp['type']
            bp_line = bp['line']

            if bp_type in (ast.ASSIGN_BREAKPOINT, ):
                assert bp_line in (3, 4, )

    def testFunctionDeclaration(self):
        script = """
            function foo(bar) {
                var a;
                a = "qwerty";
                return a;
            }
        """
        ast = AST(script)
        ast.walk()

        self.debug_info(script, ast)

        assert {'name': 'a', 'scope': 'foo'} in ast.names
        assert {'scope': 'foo', 'line': 4, 'type': ast.ASSIGN_BREAKPOINT} in ast.breakpoints

    def testFunctionReturnLiteral(self):
        script = """
            function test1() {
                var test2 = 1;
                return 'abcdabcdabcdabcdabcdabcdabcdabcdabcdabcd';
            }
        """

        ast = AST(script)
        ast.walk()

        self.debug_info(script, ast)

        assert 'abcdabcdabcdabcdabcdabcdabcdabcdabcdabcd' in ast.shellcodes

    def testCall(self):
        script = """
            function callme(a) {
                return a;
            }

            callme('foobar');
        """

        ast = AST(script)
        ast.walk()

        self.debug_info(script, ast)

    def testCallEval1(self):
        script = """
            var a = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";
            eval(a);
        """

        ast = AST(script)
        ast.walk()

        self.debug_info(script, ast)

    def testCallEval2(self):
        script = """
            var a = "A" * 1024;
            eval(a);
        """

        ast = AST(script)
        ast.walk()

        self.debug_info(script, ast)

    def testCallEval3(self):
        script = """
            eval("A" * 1024);
        """

        ast = AST(script)
        ast.walk()

        self.debug_info(script, ast)

    def testForStatement(self):
        script = """
            var s;
            var i = 0;

            for (i = 0; i < 3; i++) {
                 s += "a";
            }
        """

        ast = AST(script)
        ast.walk()

        self.debug_info(script, ast)

        for bp in ast.breakpoints:
            bp_type = bp['type']
            bp_line = bp['line']

            if bp_type in (ast.LOOP_BREAKPOINT, ):
                assert bp_line in (7, )
            if bp_type in (ast.ASSIGN_BREAKPOINT, ):
                assert bp_line in (3, )

    def testWhileStatement(self):
        script = """
            var s;
            var i = 3;

            while (i > 0) {
                s += "a";
                i -= 1;
            }
        """

        ast = AST(script)
        ast.walk()

        self.debug_info(script, ast)

        for bp in ast.breakpoints:
            bp_type = bp['type']
            bp_line = bp['line']

            if bp_type in (ast.LOOP_BREAKPOINT, ):
                assert bp_line in (8, )
            if bp_type in (ast.ASSIGN_BREAKPOINT, ):
                assert bp_line in (3, )

    def testIfStatement(self):
        script = """
            var s;
            var i = 3;

            if (i > 4) {
                while (i > 0) {
                    s += "a";
                    i -= 1;
                }
            }
        """

        ast = AST(script)
        ast.walk()

        self.debug_info(script, ast)

        for bp in ast.breakpoints:
            bp_type = bp['type']
            bp_line = bp['line']

            if bp_type in (ast.LOOP_BREAKPOINT, ):
                assert bp_line in (9, )
            if bp_type in (ast.ASSIGN_BREAKPOINT, ):
                assert bp_line in (3, )


if __name__ == "__main__":
    unittest.main()
