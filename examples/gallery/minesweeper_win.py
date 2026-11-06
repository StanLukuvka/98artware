"""Minesweeper: the board is read through the XYZZY cheat, then played by hand."""

from art98.anim import *


class MinesweeperWin(Scene):
    def construct(self):
        board = Minesweeper(at=(300, 120))
        self.add(board)
        board.find_mines()
        self.pause(0.4)
        board.clear()
        board.sign_scoreboard()
