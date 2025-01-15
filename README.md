# HoloLens Face Search Project

This project is designed for the HoloLens 2 to detect faces, send them to a laptop for searching, and then send the summary back to the HoloLens to be displayed next to the detected face. The information is displayed on a panel like "Name: Joseph", with each line for a different attribute received in the JSON data. The location of the info panel is determined by the location of the face.

## Installation Steps

### Prerequisites

- Ensure you have Visual Studio installed with the necessary components for UWP development.
- Ensure you have Python installed on your laptop.

### Setting up the HoloLens Project

1. Clone the repository:
   ```sh
   git clone https://github.com/engineer1469/HololensFaceSearch.git
   cd HololensFaceSearch
   ```

2. Open the solution file `HolographicFaceTracking.sln` in Visual Studio.

3. Build the solution by pressing `Ctrl+Shift+B` or selecting **Build** \> **Build Solution**.

4. Deploy the solution to your HoloLens device or emulator as described in the "Run the sample" section above.

### Setting up the Python Server

1. Navigate to the `server` directory:
   ```sh
   cd server
   ```

2. Create a virtual environment (optional but recommended):
   ```sh
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. Install the required Python dependencies:
   ```sh
   pip install -r requirements.txt
   ```

4. Start the server:
   ```sh
   python Server.py
   ```

## Legal Disclaimer

This project is provided "as-is" without any express or implied warranty. In no event shall the authors be held liable for any damages arising from the use of this software.
