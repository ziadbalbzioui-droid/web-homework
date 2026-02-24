

function clickCell(cell){
    if (cell.textContent !== "" || document.querySelector(".status").textContent.includes("gagné")) {
        return; 
    }
    const currentPlayer = document.querySelector(".status span").textContent;
    cell.textContent = currentPlayer;

    if (checkWin(currentPlayer)) {
        document.querySelector(".status").textContent = `Le joueur ${currentPlayer} a gagné !`;
    } else if (checkDraw()) {
        document.querySelector(".status").textContent = "Match nul !";
    } else {
        document.querySelector(".status span").textContent = currentPlayer === "X" ? "O" : "X";
    }
}

function checkWin(player) {
    const cells = document.querySelectorAll(".cell");
    const winPattern = [
        [0, 1, 2], [3, 4, 5], [6, 7, 8], 
        [0, 3, 6], [1, 4, 7], [2, 5, 8], 
        [0, 4, 8], [2, 4, 6]  
    ];
    let win = false
    for (let pattern of winPattern) {
        if (cells[pattern[0]].textContent == player && cells[pattern[1]].textContent == player && cells[pattern[2]].textContent == player){
            win = true 
        }
    }
    console.log(win)
    return win 
    
}

function checkDraw() {
    const cells = document.querySelectorAll(".cell");
    let draw = true
    console.log(cells)
    for (let cell of cells) {
        console.log(cell.textContent)
        if (cell.textContent == ""){
            draw = false
        }
    }
    console.log(draw)

    return draw

}

document.getElementById("reset").addEventListener("click", () => {
    const cells = document.querySelectorAll(".cell");
    cells.forEach(cell => cell.textContent = "");
    document.querySelector(".status span").textContent = "X";
    document.querySelector(".status").textContent = "C'est au tour de X";
});

