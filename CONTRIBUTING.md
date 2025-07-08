# Contributing to the Project

First off, thank you for considering contributing! We're thrilled you're here. This project thrives on community contributions, and we welcome
them in all forms—from bug reports and documentation improvements to new features.

This document provides guidelines to help you get started.

# ❤️ How Can I Contribute?

There are many ways to contribute, and all of them are valuable:

* 🐛 Reporting Bugs: If you find a bug, please open an issue (https://github.com/saucelabs/sauce-api-mcp/issues/new?template=bug_report.yml) and
provide as much detail as possible.
* 💡 Suggesting Enhancements: Have an idea for a new feature or an improvement? Open a feature request 
(https://github.com/saucelabs/sauce-api-mcp/issues/new?template=feature_request.yml) to start a discussion.
* 📝 Improving Documentation: If you notice something is unclear or missing in the docs, feel free to open an issue or submit a pull request
with your improvements.
* ⚙️ Submitting Pull Requests: If you're ready to write some code, we'd love to review your work!

# 🚀 Setting Up Your Development Environment


To ensure a consistent development experience, please follow these steps to set up your local environment.
## Fork and Clone the Repository

  First, fork the repository (https://github.com/saucelabs/sauce-api-mcp) to your own GitHub account. Then, clone your fork to your local
  machine:

       > git clone https://github.com/YOUR_USERNAME/your-project.git
       > cd your-project

## Create a Virtual Environment

We strongly recommend using a virtual environment to manage project dependencies. This isolates your project's packages from your global
Python installation.



    # Create a virtual environment
    python3 -m venv .venv
    
    # Activate the virtual environment
    # On macOS and Linux:
    source .venv/bin/activate

    # On Windows:
    # .venv\Scripts\activate


## Install Dependencies

With your virtual environment activated, install the required dependencies, including the development tools:

    pip install .

## Pull Request Process
  Ready to submit your changes? Great! Here’s how to do it:

### Create a new branch

    git checkout -b my-awesome-feature



### Make Your Changes
    
Write your code and add or update tests as needed.

### Commit Your Changes 

Use a clear and descriptive commit message.

    git commit -m "feat: Add support for streaming tool calls"

### Push to Your Fork

    git push origin my-awesome-feature

### Open a Pull Request

Go to the original repository on GitHub and open a pull request. Provide a clear description of your changes, why they
are needed, and link to any relevant issues.


# 🤝 Code of Conduct

We are committed to fostering an open and welcoming environment. Please review and adhere to our **Code of Conduct** (CODE_OF_CONDUCT.md).

#  📜 Licensing

By contributing to this project, you agree that your contributions will be licensed under the MIT License (LICENSE) that covers the project.
