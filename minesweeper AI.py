"""
This program captures your screen, processes the image, identifies squares that are mines and squares that are safe, and send click signals and completes the game.
I created three algorithms to determine which squares are mines and which squares are safe.
The first is the Straightforward Algorithm, where two logical operations are set in place:
1. If the number of covered squares around a number is equal to the number, then all covered squares around the number are mines.
2. If the number of flagged squares around a number is equal to the number, then all other squares around the number that are not flagged are safe.
(If you play Minesweeper you'll know what I'm talking about)
In the code the algorithm is just named calculate()
The second is Subset Elimination, where I'm comparing a square with a number and the covered squares around it, with its neighboring numbers and their neighboring covered squares, to try to calculate which squares are mines and which squares and safe.
The third is The Tank Solver Algorithm, the juice of this program, and the algorithm I am most proud of.
It will recursively iterate through all possible arrangemnets of mines given a list of locations, and count the number of times each square is a mine.
If a square is a mine in all possible arrangements, then the square is for sure a mine, and if a square is safe in all possible arrangements, then the square is for sure safe.
These algorithms increase in computational expense:
The Straightforward Algorithm and Subset Elimination provide cheap ways to solve the board, but they cannot handle all situations in Minesweeper, and that's why you need the Tank Solver Algorithm to handle all situations.
"""
from PIL.ImageGrab import grab
from numpy import array
import cv2
from time import sleep
import pyautogui
from sys import exit


class Grid:
    # board information
    board_x = 0
    board_y = 0
    board_w = 0
    board_h = 0

    d = 0  # 48 58 88

    rows = 0
    columns = 0

    mines_remaining = 99

    def __init__(self, x, y, index):
        self.x = x
        self.y = y
        self.index = index
        self.row = index // Grid.columns
        self.column = index % Grid.columns
        self.flipped = False
        self.flagged = False
        self.num = -1
        self.cent_x = x + Grid.d // 2
        self.cent_y = y + Grid.d // 2
        self.adj_grids = []
        for i in [
            -Grid.columns - 1,
            -Grid.columns,
            -Grid.columns + 1,
            -1,
            1,
            Grid.columns - 1,
            Grid.columns,
            Grid.columns + 1,
        ]:
            n = self.index + i
            if (
                n >= 0
                and n < Grid.rows * Grid.columns
                and abs(self.column - n % Grid.columns) <= 1
            ):
                self.adj_grids.append(n)
        self.prob = 0

    # returns adjacent squares that are not flagged
    def adj_unflagged(self):
        l = []
        for i in self.adj_grids:
            if grids[i].flipped == False and grids[i].flagged == False:
                l.append(i)
        return l

    # returns the number of flagged squares around a square
    def n_mines(self):
        n = 0
        for i in self.adj_grids:
            if grids[i].flagged == True:
                n += 1
        return n

    # returns squares that are numbers around a square
    def adj_nums(self):
        l = []
        for i in self.adj_grids:
            if i in nums:
                l.append(i)
        return l

    # The Straightforward Algorithm
    def calculate(self):
        unflagged = self.adj_unflagged()
        for i in unflagged:
            grids[i].prob = (self.num - self.n_mines()) * 100 / len(unflagged)
        n = 0
        mines_found = 0
        for i in self.adj_unflagged():
            # If the number of flagged squares around a number is equal to the number
            if grids[i].prob == 0:
                # click on the square
                grids[i].click()
                n += 1
            # If the number of covered squares around a number is equal to the number
            elif grids[i].prob == 100:
                # right-click on the square
                grids[i].right_click()
                n += 1
                mines_found += 1
        return n, mines_found

    # clicks a square
    def click(self):
        pyautogui.click(
            (self.cent_x + Grid.board_x) / 2, (self.cent_y + Grid.board_y) / 2
        )
        self.flipped = True

    # right-clicks a square
    def right_click(self):
        pyautogui.rightClick(
            (self.cent_x + Grid.board_x) / 2, (self.cent_y + Grid.board_y) / 2
        )
        self.flagged = True

    # Subset Elimination
    def subset_elimination(self):
        n = 0
        mines_found = 0
        # for all adjacent squares that are numbers
        for i in self.adj_nums():
            # get their adjacent covered squares
            list2 = grids[i].adj_unflagged()
            # get all covered squares around the original square
            list1 = self.adj_unflagged()
            # if list2 doesn't have anything unique to itself
            if not any(set(list2) - set(list1)):
                # unique locations to list1
                unique = list(set(list1) - set(list2))
                # calculate
                diff = (self.num - self.n_mines()) - (grids[i].num - grids[i].n_mines())
                if len(unique) == diff:
                    for j in unique:
                        grids[j].right_click()
                        n += 1
                        mines_found += 1
                elif diff == 0:
                    for j in unique:
                        n += 1
                        grids[j].click()
        return n, mines_found

    @staticmethod
    # finds paths used by the Tank Solver Algorithm
    def find_path(n, previous, useful_unflagged):
        base_case = True
        both_ways = False
        l = []
        # the list containing locations of previous cases
        previous.append(n)
        # for numbers around
        for k in grids[n].adj_nums():
            # for their adjacent covered squares
            for i in grids[k].adj_unflagged():
                # if it's not a previous location and is a valid location
                if not i in previous and i in useful_unflagged:
                    base_case = False
                    # recursive case
                    temp = Grid.find_path(i, previous, useful_unflagged)
                    # this is for if the entry point isn't at an end of the path
                    if both_ways:
                        for j in temp:
                            l.insert(0, j)
                    else:
                        l = temp
                        l.insert(0, n)
                    both_ways = True
        # if it couldn't find any more locations, it means it's at an end and has reached the base case
        if base_case:
            return [n]
        return l

    # a help function for The Tank Solver Algorithm
    # determines if a square has to be a mine, or else would make the arrangement not possible
    def has_to(self, locations, virtual_mines):
        # for all adjacent numbers
        for i in self.adj_nums():
            spots_left = 0
            n = 0
            for j in grids[i].adj_grids:
                # the number of their spots that have not been iterated through already
                if j in locations:
                    spots_left += 1
                # the number of virtual mines around the number
                if j in virtual_mines:
                    n += 1
            # the number of mines to be placed to satisfy its number
            mines_to_be_placed = grids[i].num - grids[i].n_mines() - n
            # if spots left equal mines to be placed, then the location must be a mine
            if spots_left == mines_to_be_placed:
                return True
        return False

    # another help function for The Tank Solver Algorithm
    # deternines if it's possible for a square to be a mine, or else would make the arrangement not possible
    def possible(self, virtual_mines):
        # for all adjacent numbers
        for i in self.adj_nums():
            n = 0
            for j in grids[i].adj_grids:
                # the number of virtual mines around the number
                if j in virtual_mines:
                    n += 1
            # if the number has already been satisfied, then the location must not be a mine, or else would make the number of mines around the number too many
            if grids[i].num - grids[i].n_mines() - n == 0:
                return False
        return True

    @staticmethod
    # The Tank Solver Algorithm
    def tank_solver(locations, virtual_mines, dict, mines_remaining):
        # if there aren't any more possible mines
        if mines_remaining < 0:
            return 0
        # if locations is empty, a base case has been reached
        if not locations:
            for i in virtual_mines:
                dict[i] += 1
            return 1
        # the count for the number of possible arrangements
        n = 0
        # if the location doesn't have to be a mine, proceed to the next call stack pretending that this location is safe
        if not grids[locations[0]].has_to(locations, virtual_mines):
            # pop the current location for the next call stack
            temp = locations.pop(0)
            n += Grid.tank_solver(locations, virtual_mines, dict, mines_remaining)
            # insert it back
            locations.insert(0, temp)
        # if the location is possible to be a mine, proceed to the next call stack pretending that this location is a mine
        if grids[locations[0]].possible(virtual_mines):
            # append the current location to virtual mines for the next call stack
            virtual_mines.append(locations[0])
            # pop this location as well
            temp = locations.pop(0)
            n += Grid.tank_solver(locations, virtual_mines, dict, mines_remaining - 1)
            # insert it back
            locations.insert(0, temp)
            # remove it from virtual mines
            virtual_mines.remove(locations[0])
        return n


# captures your screen
def screen_shot():
    im = grab()
    im_np = array(im)
    im_np = cv2.cvtColor(im_np, cv2.COLOR_RGB2BGR)
    return im_np


# processes the image
# my strategy for processing the image is to use Opencv's findContours() function to find the board, read the color of the center pixel of every square to determine it's number
def proc_img():
    # preprocessing
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    _, thresh = cv2.threshold(blur, 183, 255, cv2.THRESH_BINARY_INV)

    # finding the location of the board
    if Grid.board_x == 0:
        contours, _ = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        x = 0
        for contour in contours:
            area = cv2.contourArea(contour)
            if area in [646379, 905279, 1197799]:
                x, y, w, h = cv2.boundingRect(contour)
                break
        if x == 0:
            print("board not found")
            return [], False
        Grid.board_x = x
        Grid.board_y = y
        Grid.board_w = w
        Grid.board_h = h

    # focusing on the region of interest (roi) and preprocessing it
    roi = img[
        Grid.board_y : Grid.board_y + Grid.board_h,
        Grid.board_x : Grid.board_x + Grid.board_w,
    ]
    roi_blur = blur[
        Grid.board_y : Grid.board_y + Grid.board_h,
        Grid.board_x : Grid.board_x + Grid.board_w,
    ]
    _, roi_thresh = cv2.threshold(roi_blur, 190, 255, cv2.THRESH_BINARY_INV)  # 184, 190
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    roi_thresh = cv2.dilate(roi_thresh, kernel, iterations=1)

    # finding information about the board and initializing class instances
    if Grid.d == 0:
        contours, _ = cv2.findContours(
            roi_thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
        )
        for contour in contours:
            area = cv2.contourArea(contour)
            if area > 2000 and area < 8000:
                _, _, w, _ = cv2.boundingRect(contour)
                break
        rows = round(roi.shape[0] / (w + 2))
        columns = round(roi.shape[1] / (w + 2))
        Grid.d = w
        Grid.rows = rows
        Grid.columns = columns
        for i in range(rows):
            for j in range(columns):
                grids.append(Grid(1 + j * (w + 2), 1 + i * (w + 2), i * columns + j))

    # reading numbers off of every square
    # these are hand tested color values for every number
    #            lighter square, darker square, when hovering on a lighter square, when hovering on a darker square
    # unflipped: 101 214 179,    94  208 172,   137 224 198,                       131 220 192
    # 0:         163 195 223,    157 185 210
    # 1:         203 116 56
    # 2:         114 166 145,    111 161 139
    # 3:         63  71  196,    62  70  195
    # 4:         158 119 170,    155 114 163
    # 5:         54  149 240
    # 6:         163 173 134,    160 167 127
    # 7:         119 137 152,    115 131 144
    # I choose to use their red value to determine their numbers
    # mapped values for red
    r_mp = {
        223: 0,
        210: 0,
        56: 1,
        57: 1,
        145: 2,
        139: 2,
        196: 3,
        195: 3,
        170: 4,
        163: 4,
        240: 5,
        134: 6,
        127: 6,
        152: 7,
        144: 7,
    }
    # list to store squares that are numbers on the board
    nums = []
    new_board = True
    # for every square
    for i in grids:
        # read its green and red value of its center pixel
        g = roi.item(i.cent_y, i.cent_x, 1)
        r = roi.item(i.cent_y, i.cent_x, 2)
        # if it is an uncovered square
        if g not in [214, 208, 224, 220]:
            i.flipped = True
            new_board = False
            if r in r_mp:
                if i.num == -1:
                    # saving its number
                    i.num = r_mp[r]
                # append it to nums if it will be a useful number
                if r_mp[r] and i.adj_unflagged():
                    nums.append(i.index)
            # unexpected color, something is wrong with the board
            else:
                print(
                    f"abnormal board at (starting from 0) row, column({i.row}, {i.column})"
                )
                print(
                    f"its color is bgr({roi.item(i.cent_y, i.cent_x, 0)}, {roi.item(i.cent_y, i.cent_x, 1)}, {roi.item(i.cent_y, i.cent_x, 2)})"
                )
                cv2.destroyAllWindows()
                exit()
    # if it's a new board, reset variables
    if new_board:
        for i in grids:
            i.num = -1
            i.prob = 0
            i.flipped = False
            i.flagged = False
        # click the center square to set off the game
        index = int(Grid.rows / 2 * Grid.columns + Grid.columns / 2)
        grids[index].click()
        sleep(0.1)

    # display the computer vision of the game to a window
    for i in grids:
        cv2.rectangle(
            roi, (i.x, i.y), (i.x + Grid.board_w, i.y + Grid.board_h), (0, 255, 0), 2
        )
        cv2.putText(
            roi,
            str(i.num),
            (i.cent_x, i.cent_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 0, 0),
            1,
            cv2.LINE_AA,
        )
    cv2.imshow("Screen(Computer Vision)", roi)
    cv2.waitKey(1)
    return nums, True


def solve():
    n = 0
    mines_found = 0
    # for every square that is a number
    for i in nums:
        # use the Straightforward Algorithm and Subset Elimination
        n1, mines_found1 = grids[i].calculate()
        n += n1
        mines_found += mines_found1
        n1, mines_found1 = grids[i].subset_elimination()
        n += n1
        mines_found += mines_found1

    # identify the covered squares to be iterated through by the Tank Solver Algorithm
    useful_unflagged = []
    for i in grids:
        if i.num > 0:
            for j in i.adj_unflagged():
                if not j in useful_unflagged:
                    useful_unflagged.append(j)
    # since the Tank Solver Algorithm takes 2^n iterations, then it would be better to divide up the list into smaller independent pieces to reduce run time
    # for example, it would be faster to iterate 2^10 + 2^7 times then to iterate 2^17 times.
    list_locations = []
    while useful_unflagged:
        list_locations.append(Grid.find_path(useful_unflagged[0], [], useful_unflagged))
        useful_unflagged = [j for j in useful_unflagged if j not in list_locations[-1]]
    # use the Tank Solver Algorithm
    for j in list_locations:
        if len(j) >= 29:
            print(f"there was an iteration with length {len(j)}")
        dict = {k: 0 for k in j}
        arrangements = Grid.tank_solver(j, [], dict, Grid.mines_remaining - mines_found)
        for k in dict:
            if dict[k] == arrangements:
                grids[k].right_click()
                n += 1
                mines_found += 1
            elif dict[k] == 0:
                grids[k].click()
                n += 1

    # end game tactics
    # if neither The Straightforward Algorithm, Subset Elimination, and The Tank Solver Algorithm could solve anything, then we're at an end-game situation
    if n == 0:
        # we'll need to iterate through all remaining tiles with The Tank Solver Algorithm
        remaining_tiles = []
        for i in grids:
            if i.flipped == False and i.flagged == False:
                remaining_tiles.append(i.index)
        # if there are more than 10 remaining tiles, it's a false alarm, we don't want to iterate through all remaining tiles
        if len(remaining_tiles) <= 10:
            print("end game")
            # use Tank Solver
            dict = {i: 0 for i in remaining_tiles}
            Grid.tank_solver(
                remaining_tiles, [], dict, Grid.mines_remaining - mines_found
            )
            for i in dict:
                if dict[i] == min(dict.values()):
                    grids[i].click()
    # keep track of mines remaining
    Grid.mines_remaining -= mines_found

if __name__ == "__main__":
    # the list to store all square objects
    grids = []
    # cancel the pause to allow for highest speed
    pyautogui.PAUSE = 0
    # window to showcase the computer vision
    cv2.namedWindow("Screen(Computer Vision)", cv2.WINDOW_NORMAL)
    found = False
    while True:
        sleep(0.81)
        # if the board has been found on the screen, move the cursor out of the way to avoid interference and take a screen shot
        if found:
            pyautogui.moveTo(460, 80)
        img = screen_shot()
        # process the image
        nums, found = proc_img()
        if found:
            # solve
            solve()