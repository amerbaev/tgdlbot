import logging

def load_whitelist(filepath: str = "whitelist.txt") -> set[int]:
    """Load user IDs from whitelist file.

    Args:
        filepath: Path to whitelist file

    Returns:
        Set of allowed user IDs

    Raises:
        FileNotFoundError: If whitelist file missing
        ValueError: If no valid user IDs found
    """
    user_ids = set()

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()

                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue

                # Parse user ID
                try:
                    user_id = int(line)
                    user_ids.add(user_id)
                except ValueError:
                    logging.warning(f'Invalid user ID in whitelist: {line}')

    except FileNotFoundError:
        raise FileNotFoundError(f'whitelist.txt not found. Create it with allowed user IDs.')

    if not user_ids:
        raise ValueError('No valid user IDs found in whitelist.txt')

    return user_ids